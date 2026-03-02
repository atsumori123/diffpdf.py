import os
import sys
import fitz
import cv2
import numpy as np
import json
from skimage.metrics import structural_similarity as ssim

# ---------------------------------------------------------
# テキストの行データを抽出する（bbox付き）
# ---------------------------------------------------------
def extract_lines_with_bboxes(page_no, page):
	lines_data = []
	
	# ページ内の全ての単語を取得
	words = page.get_text("words")
	if not words: return lines_data

	# y軸の座標（top）が近いものを同じ行とみなしてグループ化する
	# pdfplumberのデフォルトでは、微妙なズレがあるため、
	# 同じ行として扱うための閾値（tolerance）を考慮すると安定します
	current_line_text = []

	# 単語の端から端までの初期値を設定
	min_x0, min_y0, max_x1, max_y1, text, _, _, _ = words[0]
	current_top = min_y0

	for x0, y0, x1, y1, text, _, _, _ in words:
		# 前の単語と y座標が大きく離れたら新しい行とみなす
		if abs(y0 - current_top) > 3: 
			# 前の行を保存
			lines_data.append({
				"page": page_no + 1,
				"text": " ".join(current_line_text),
				"bbox": (min_x0, min_y0, max_x1, max_y1) # (左, 上, 右, 下)
			})
			# 新しい行の初期化
			current_line_text = []
			current_line_text.append(text)
			current_top = y0
			min_x0, min_y0, max_x1, max_y1 = x0, y0, x1, y1
		else:
			current_line_text.append(text)
			min_x0 = min(min_x0, x0)
			max_x1 = max(max_x1, x1)
			max_y1 = max(max_y1, y1)

	# 最後の行を追加
	lines_data.append({
		"page": page_no + 1,
		"text": " ".join(current_line_text),
		"bbox": (min_x0, min_y0, max_x1, max_y1)
	})
			
	return lines_data


# ---------------------------------------------------------
# テキスト比較
# ---------------------------------------------------------
def compare_line(page_no, page1, page2):
	# テキスト行を抽出する
	lines1 = extract_lines_with_bboxes(page_no, page1)
	lines2 = extract_lines_with_bboxes(page_no, page2)

	# Y座標を昇順に並び替え
	lines1.sort(key=lambda x: x["bbox"][1])
	lines2.sort(key=lambda x: x["bbox"][1])

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

	# ヘッダーとフッター除外
	header_ofs = HEADER_HEIGHT
	footer_ofs = FOOTER_HEIGHT
	line_diffs = [v for v in line_diffs if v[3] >= header_ofs and v[1] <= PAGE_HEIGHT - footer_ofs]

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
		return img, (0, 0, img.shape[1], img.shape[0])

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
# fitzページをOpenCVで扱う画像形式に変換
# ---------------------------------------------------------
def pdf2BGR(page):
	# ページをpixmapに変換
	pix = page.get_pixmap(colorspace=fitz.csGRAY)

	# NumPy配列に変換してOpenCV用にBGR形式へ
	img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

	return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------
# 指定サイズに合わせて画像の右と下に空白を入れる
# ---------------------------------------------------------
def pad_image(img, target_height, target_width):
	h, w = img.shape[:2]

	# 右側と下側の不足サイズ
	bottom = target_height - h
	right = target_width - w

	# 拡張
	padded_img = cv2.copyMakeBorder(img, 0, bottom, 0, right, cv2.BORDER_CONSTANT, value=(255, 255, 255))

	return padded_img


# ---------------------------------------------------------
# テキストとイメージで重なっている差異を削除
# ---------------------------------------------------------
def remove_overlap_diffs(img_diffs, line_diffs):
	new_diffs = []

	# ここで確実に fitz.Rect に変換
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
# 差異部分の面積より差異とみなすか
# ---------------------------------------------------------
def is_valid_difference(bbox, threshold):
	w = bbox[2] - bbox[0]
	h = bbox[3] - bbox[1]
	area = w * h
	return area > threshold


# ---------------------------------------------------------
# 画像表示(デバッグ用)
# ---------------------------------------------------------
def disp_image(img1, img2, title):
	h_img = cv2.hconcat([img1, img2])
	cv2.imshow(title, h_img)
	cv2.waitKey(0)
	cv2.destroyAllWindows()


# ---------------------------------------------------------
# イメージの比較
# ---------------------------------------------------------
def compare_image(page_no, page1, page2):
	# pdf --> BGR に変換
	img1 = pdf2BGR(page1)
	img2 = pdf2BGR(page2)

	# ヘッダー・フッター除去
	img1, header_offset1 = crop_header_footer(img1)
	img2, header_offset2 = crop_header_footer(img2)
	#print(f"header_offset1={header_offset1}, header_offset2={header_offset2}")

	# 余白除去
	img1, trim1 = trim_margin(img1)
	img2, trim2 = trim_margin(img2)
	
	# サイズを大きい画像に合わせて揃える
	h = max(img1.shape[0], img2.shape[0])
	w = max(img1.shape[1], img2.shape[1])
	img1 = pad_image(img1, h, w)
	img2 = pad_image(img2, h, w)
	#disp_image(img1, img2, "SSIM")

	# グレースケール化
	g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
	g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

	# グレースケールの階調を変更
	if 'GRAY_GRADATION' in globals():
		g1 = (g1 // GRAY_GRADATION) * GRAY_GRADATION
		g2 = (g2 // GRAY_GRADATION) * GRAY_GRADATION

	# フォント差異吸収のため軽くぼかす
	g1 = cv2.GaussianBlur(g1, (5, 5), 0)
	g2 = cv2.GaussianBlur(g2, (5, 5), 0)

	# SSIM比較
	#disp_image(g1, g2, "SSIM")
	score, diff = ssim(g1, g2, full=True)
	diff = (diff * 255).astype("uint8")

	# SSIMの差分マップ(0～255)を2値化して差分領域を抽出
	# 差分がある部分を白くする
	# ノイズ除去のため膨張処理(dilate)
	_, th = cv2.threshold(diff, CV2_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
	th = cv2.dilate(th, None, iterations=2)

	# 差分領域の輪郭を取得
	contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

	# 差異部分単位でSSIMスコア判定する際、回りの領域も少し含める
	pad = SSIM_PAD if 'SSIM_PAD' in globals() else 0

	img_diffs = []
	for cnt in contours:
		x, y, w, h = cv2.boundingRect(cnt)

		# 前処理画像 → 元画像の座標に変換
		org_x = x + trim2[0]
		org_y = y + trim2[1] + header_offset2
		bbox = (org_x, org_y, org_x+w, org_y+h)
		
		# 面積が小さい差異は無視
		if not is_valid_difference(bbox, VALID_AREA_SIZE):
			continue

		# 差分領域を切り出し
		x1 = max(0, x - pad)
		y1 = max(0, y - pad)
		x2 = min(g1.shape[1], x + w + pad)
		y2 = min(g1.shape[0], y + h + pad)
		roi1 = g1[y1:y2, x1:x2]
		roi2 = g2[y1:y2, x1:x2]

		# 差分領域のSSIMスコアを計算
		try:
			roi_score = ssim(roi1, roi2, full=False)
			#print(f"x={x}, y={y}, w={w}, h={h}, roi_score={roi_score}")
		except ValueError:
			# サイズが合わないなどのエラー対策
			continue

		# SSIMスコアが0.98以上なら差異とみなさない
		if roi_score < 0.98:
			img_diffs.append(bbox)

	return img_diffs


# ---------------------------------------------------------
# ヘッダーとフッター領域確認用
# ---------------------------------------------------------
def check_header_footer_area(pdf, page_no):
	# pdf --> BGR に変換
	img = pdf2BGR(pdf, page_no)

	# ヘッダー・フッター除去
	img, _ = crop_header_footer(img)

	# 表示
	cv2.imshow("header, footer", img)
	cv2.waitKey(0)
	cv2.destroyAllWindows()


# ---------------------------------------------------------
# 差異箇所をオーバレイ
# ---------------------------------------------------------
def diff_overlay(page, line_diffs, image_diffs):
	# キャンバスを作る
	text_shape = page.new_shape()

	# テキストの差異をキャンバスに描く
	for bbox in line_diffs:
		text_shape.draw_rect(bbox)

	# キャンバスに描いた図形に色や線のスタイルを適用して描画を確定させる
	text_shape.finish(fill=(1,0,0), color=None, fill_opacity=0.3)

	# ページに反映
	text_shape.commit()

	# キャンバスを作る
	image_shape = page.new_shape()

	# 画像の差異をキャンバスに描く
	for bbox in image_diffs:
		image_shape.draw_rect(bbox)

	# キャンバスに描いた図形に色や線のスタイルを適用して描画を確定させる
	image_shape.finish(fill=(0,0,1), color=None, fill_opacity=0.3)

	# ページに反映
	image_shape.commit()

	return page.get_pixmap()


# ---------------------------------------------------------
# 比較メイン処理
# ---------------------------------------------------------
def compare_pdfs(pdf1, pdf2, output_dir):
	with fitz.open(pdf1) as doc1, fitz.open(pdf2) as doc2:
		# ページ数が大きい方を採用
		max_page_num = max(len(doc1), len(doc2))

		# ページ数分繰り返す
		for i in range(max_page_num):
			line_diffs = image_diffs = []

			if i >= len(doc1) or i >= len(doc2):
				print(f"[SKIP] {i+1} / {max_page_num}  比較ページなし")
				continue

			# --------------
			# テキスト比較
			# --------------
			if "text" in COMPARISON_TYPE:
				line_diffs = compare_line(i, doc1[i], doc2[i])

			# --------------
			# 画像比較
			# --------------
			if "image" in COMPARISON_TYPE:
				image_diffs = compare_image(i, doc1[i], doc2[i])

			# ------------------------------------------------------
			# 画像比較結果からテキスト比較と重複する部分は除外する
			# ------------------------------------------------------
#			image_diffs = remove_overlap_diffs(image_diffs, line_diffs)

			# --------------
			# 結果の出力
			# --------------
			if len(line_diffs) + len(image_diffs):
				# pdf2のページをベースにして差異の部分をオーバレイ
				diff_img = diff_overlay(doc2[i], line_diffs, image_diffs)
				fname = f"{output_dir}/diff_page_{i+1:03}.png"
				diff_img.save(fname)
				print(f"[DIFF] {i+1} / {max_page_num}  -->	{fname}")
			else:
				print(f"[ OK ] {i+1} / {max_page_num}")

	return


# ---------------------------------------------------------
# メイン
# ---------------------------------------------------------
if __name__ == "__main__":
	if len(sys.argv) < 3:
		print('Arguments are too short')
		exit()

	print(f"pdf1 : {sys.argv[1]}")
	print(f"pdf2 : {sys.argv[2]}")
	print("----- settings -------------")

	# 設定情報をロード
	with open("./settings.json", "r") as f:
		settings = json.load(f)
		for key, value in settings.items():
			globals()[key.upper()] = value
			print(f"{key.upper():16} = {value}")

	print("----------------------------")

	if sys.argv[2] == "-hf":
		check_header_footer_area(sys.argv[1], 1)
		exit()

	# ページの高さを取得
	with fitz.open(sys.argv[1]) as f:
		PAGE_HEIGHT = f[0].rect.height

	# 出力ディレクトリ作成
	os.makedirs("output", exist_ok=True)

	# 比較
	compare_pdfs(sys.argv[1], sys.argv[2], "output")

