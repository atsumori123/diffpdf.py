import os
import fitz
import cv2
import argparse
import numpy as np
import pdfplumber
from skimage.metrics import structural_similarity as ssim

# ---------------------------------------------------------
# 定義
# ---------------------------------------------------------
HEADER_HEIGHT = 0			# PDF2のヘッダー領域の高さ(px)
FOOTER_HEIGHT = 0			# PDF2のフッター領域の高さ(px)
PAGE_HEIGHT = 0				# ページの高さ(px)
DIFF_THRESHOLD = 200		# 差分の閾値。150～230が推奨。(値が小さいほど小さな差分を検出しやすくなる)
DPI = 200


# ---------------------------------------------------------
# ヘッダー・フッター除外
# ---------------------------------------------------------
def remove_header_footer(lines):
	filtered = []

	#ヘッダー終端とフッター開始座標を計算
	header_y = HEADER_HEIGHT
	footer_y = PAGE_HEIGHT - FOOTER_HEIGHT
	#print(f"header={header_y}, footer_y={footer_y}")

	# ブロックのY座標がヘッダー領域またはフッタ領域にかかっているか確認
	for l in lines:
		y0, y1 = l["bbox"][1], l["bbox"][3]
		if y1 < header_y or y0 > footer_y:
			continue
		filtered.append(l)

	return filtered


# ---------------------------------------------------------
# テキスト差分 bbox と重ならない領域を図差分と判定
# ---------------------------------------------------------
def extract_figure_diffs2(diff_mask, line_diffs, scale):
	mask = diff_mask.copy()

	for bbox in line_diffs:
		x0, y0, x1, y1 = [int(v * DPI / 72) for v in bbox]
		mask[y0:y1, x0:x1] = 0

	# 図差分の bbox 抽出
	contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
	figure_bboxes = []

	for cnt in contours:
		x, y, w, h = cv2.boundingRect(cnt)
		if w * h > 200:  # 小さすぎるノイズ除外
			figure_bboxes.append((x, y, x + w, y + h))

	return figure_bboxes


# ---------------------------------------------------------
# テキストの行データを抽出する（bbox付き）
# ---------------------------------------------------------
def extract_lines_with_bboxes(page_no, page):
	lines_data = []
	
	words = page.extract_words()
	if not words:
		return lines_data

	# y軸の座標（top）が近いものを同じ行とみなしてグループ化する
	# pdfplumberのデフォルトでは、微妙なズレがあるため、
	# 同じ行として扱うための閾値（tolerance）を考慮すると安定します
	current_line_text = []
	current_top = words[0]["top"]
	line_bboxes = []

	# ページの端から端までの初期値を設定
	min_x0, min_top = words[0]["x0"], words[0]["top"]
	max_x1, max_bottom = words[0]["x1"], words[0]["bottom"]

	for word in words:
		# 前の単語と y 座標が大きく離れたら新しい行とみなす
		if abs(word["top"] - current_top) > 3: 
			# 前の行を保存
			lines_data.append({
				"page": page_no,
				"text": " ".join(current_line_text),
				"bbox": (min_x0, min_top, max_x1, max_bottom) # (左, 上, 右, 下)
			})
			# 新しい行の初期化
			current_line_text = [word["text"]]
			current_top = word["top"]
			min_x0, min_top, max_x1, max_bottom = word["x0"], word["top"], word["x1"], word["bottom"]
		else:
			current_line_text.append(word["text"])
			min_x0 = min(min_x0, word["x0"])
			max_x1 = max(max_x1, word["x1"])
			max_bottom = max(max_bottom, word["bottom"])

	# 最後の行を追加
	lines_data.append({
		"page": page_no,
		"text": " ".join(current_line_text),
		"bbox": (min_x0, min_top, max_x1, max_bottom)
	})
			
	return lines_data


# ---------------------------------------------------------
# テキスト比較
# ---------------------------------------------------------
def compare_text(lines1, lines2):
	# 行数の多い方に合わせてループ
	max_lines = max(len(lines1), len(lines2))

	line_diffs = []
	for i in range(max_lines):
		line1 = lines1[i] if i < len(lines1) else None
		line2 = lines2[i] if i < len(lines2) else None

		# pdf1で削除
		if line1 == None:
			line_diffs.append(line2["bbox"])
			continue

		# pdf2で削除
		if line2 == None:
			line_diffs.append(line1["bbox"])
			continue

		# テキスト内容を比較
		if line1["text"] != line2["text"]:
			line_diffs.append(line2["bbox"])

	# ヘッダーとフッター領域の差異は除外
	header_ofs = HEADER_HEIGHT * DPI / 72
	footer_ofs = FOOTER_HEIGHT * DPI / 72
	line_diffs = [v for v in line_diffs if v[1] >= header_ofs and v[1] <= PAGE_HEIGHT - footer_ofs]

	return line_diffs

# ---------------------------------------------------------
# 余白を自動トリミング
# ---------------------------------------------------------
def trim_margin(img, threshold=250):
	# 色ではなく明暗で判定するため白黒画像(2値化)に変換する
	gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	_, th = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

	# 余白以外(文字や図)を抽出。(255 - th)で、
	# 文字・図→白(255)
	# 余白→黒(0)
	coords = cv2.findNonZero(255 - th)
	if coords is None:
		return img

	# 文字、図が存在する最小の矩形を計算し、その領域を切り出す
	x, y, w, h = cv2.boundingRect(coords)
	return img[y:y+h, x:x+w], (x, y, w, h)


# ---------------------------------------------------------
# ヘッダー・フッター除去
# ---------------------------------------------------------
def crop_header_footer(img):
	# 画像の高さを取得
	h = img.shape[0]

	# ヘッダー領域以降からフッターまでを切り出す
	return img[HEADER_HEIGHT:h-FOOTER_HEIGHT, :], HEADER_HEIGHT


# ---------------------------------------------------------
# pdfの指定ページをOpenCVで扱う画像形式に変換
# ---------------------------------------------------------
def pdf2BGR(pdf, page_no):
	with fitz.open(pdf) as f:
		# ページをpixmapに変換
		page = f[page_no - 1]
		pix = page.get_pixmap(colorspace=fitz.csGRAY)

		# NumPy配列に変換してOpenCV用にBGR形式へ
		img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
		img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

	return img_bgr


# ---------------------------------------------------------
# テキストとイメージで重なっている差異を削除
# ---------------------------------------------------------
def remove_overlap_diffs(img_diffs, line_diffs):
	new_diffs = []

	# ここで確実に fitz.Rect に変換します
	rects1 = [fitz.Rect(b) for b in img_diffs]
	rects2 = [fitz.Rect(b) for b in line_diffs]

	for i, r1 in enumerate(rects1):
		flag = 0
		for j, r2 in enumerate(rects2):
			# intersects は一部でも重なれば True を返す
			if r1.intersects(r2):
				flag = 1
				#print(f"bbox1[{i}] と bbox2[{j}] は重なっています。")
		if not flag:
			new_diffs.append(img_diffs[i])

	return new_diffs
		

# ---------------------------------------------------------
# イメージの比較
# ---------------------------------------------------------
def compare_image(pdf1, pdf2, page_no):
	# pdf --> BGR に変換
	img1 = pdf2BGR(pdf1, page_no)
	img2 = pdf2BGR(pdf2, page_no)

	# 余白除去
	img1, trim1 = trim_margin(img1)
	img2, trim2 = trim_margin(img2)

	# ヘッダー・フッター除去
	img1, header_offset1 = crop_header_footer(img1)
	img2, header_offset2 = crop_header_footer(img2)
	#print(f"header_offset1={header_offset1}, header_offset2={header_offset2}")
	
	#cv2.imshow("Display Window", img1)
	#cv2.waitKey(0)
	#cv2.destroyAllWindows()

	# サイズを小さい画像に合わせて揃える
	h = min(img1.shape[0], img2.shape[0])
	w = min(img1.shape[1], img2.shape[1])
	img1 = img1[:h, :w]
	img2 = img2[:h, :w]

	# グレースケール化
	g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
	g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

	# フォント差異吸収のため軽くぼかす
	g1 = cv2.GaussianBlur(g1, (5, 5), 0)
	g2 = cv2.GaussianBlur(g2, (5, 5), 0)

	# SSIM比較
	score, diff = ssim(g1, g2, full=True)
	diff = (diff * 255).astype("uint8")
	#print(f"score={score}")

	# SSIMの差分マップ(0～255)を2値化して差分領域を抽出
	# 差分がある部分を白くする
	# ノイズ除去のため膨張処理(dilate)
	_, th = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
	th = cv2.dilate(th, None, iterations=2)

	# 差分領域の輪郭を取得
	contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

	img_diffs = []
	for cnt in contours:
		x, y, w, h = cv2.boundingRect(cnt)

		# 前処理画像 → 元画像の座標に変換
		org_x = x + trim2[0]
		org_y = y + trim2[1] + header_offset2

		img_diffs.append((org_x, org_y, org_x+w, org_y+h))

	return img_diffs


# ---------------------------------------------------------
# 差異箇所をオーバレイ
# ---------------------------------------------------------
def diff_overlay(page, line_diffs, img_diffs):
	# ページを画像(Pillow)に変換
	img = page.to_image(DPI)

	# テキストの差異をオーバレイ
	for diff in line_diffs:
#		bbox2 = tuple(x * dpi / 72 for x in bbox)
		img.draw_rect(diff, fill=(255,0,0,85), stroke=None)

	# 画像の差異をオーバレイ
	for diff in img_diffs:
		img.draw_rect(diff, fill=(0,0,255,85), stroke=None)

	return img


# ---------------------------------------------------------
# メイン処理
# ---------------------------------------------------------
def compare_pdfs(pdf1, pdf2, output_dir):
	with pdfplumber.open(pdf1) as f1, pdfplumber.open(pdf2) as f2:
		# pdf1とpdf2で大きい方のページ数を取得
		max_page_num = max(len(f1.pages), len(f2.pages))
		#print(f"max_page_num={max_page_num}")

		# ページ内のテキストデータを取得
		line_diffs = img_diffs = []
		for i in range(max_page_num):
			# テキスト行を抽出する
			lines1 = extract_lines_with_bboxes(i+1, f1.pages[i])
			lines2 = extract_lines_with_bboxes(i+1, f2.pages[i])

			# ヘッダー・フッター除外
			lines1 = remove_header_footer(lines1)
			lines2 = remove_header_footer(lines2)

			# テキスト比較
			line_diffs = compare_text(lines1, lines2)

			# 画像差分
			img_diffs = compare_image(pdf1, pdf2, i)

			# テキストと重複部分を除去
			img_diffs = remove_overlap_diffs(img_diffs, line_diffs)

			# ページを画像変換して差異の部分をオーバレイ
			diff_img = diff_overlay(f2.pages[i], line_diffs, img_diffs)
			fname = f"{output_dir}/diff_page_{i+1:03}.png"
			diff_img.save(fname)
			print(f"{i+1} ページ目に差異があります -->  {fname}")

	return


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("pdf1", help="pdf file 1")
	parser.add_argument("pdf2", help="pdf file 2")
	parser.add_argument("-header", help="header height (px) (default:0)")
	parser.add_argument("-fotter", help="footer height (px) (default:0)")
	args = parser.parse_args()

	# ヘッダとフッターの高さ
	if args.header: HEADER_HEIGHT = int(args.header)
	if args.fotter: FOOTER_HEIGHT = int(args.fotter)

	# ページの高さを取得
	with fitz.open(args.pdf1) as f:
		PAGE_HEIGHT = f[0].rect.height

	# 出力ディレクトリ作成
	os.makedirs("output", exist_ok=True)

	compare_pdfs(args.pdf1, args.pdf2, "output")

