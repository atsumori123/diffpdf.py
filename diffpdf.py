import os
import sys
import fitz
import diff_char
import diff_image
import settings

# ---------------------------------------------------------
# 差異箇所をオーバレイ
# 
# 引数
#	page_no		  : ページ番号
#	page1		  : オーバレイのベースとなるページ (PyMuPDF)
#	page2		  : オーバレイのベースとなるページ (PyMuPDF)
#	added_bboxes  : 追加された要素のリスト (bbox)
#	removed_bboxes: 削除された要素のリスト (bbox)
#	output_dir	  : 差分結果出力先ディレクトリ
# 戻り値
#	なし
# ---------------------------------------------------------
def output_diff(page_no, page1, page2, added_bboxes, removed_bboxes, output_dir):
	# キャンバスを作る
	text1_shape = page1.new_shape()

	# テキストの差異をキャンバスに描く
	for bbox in removed_bboxes:
		text1_shape.draw_rect(bbox)

	# キャンバスに描いた図形に色や線のスタイルを適用して描画を確定させる
	text1_shape.finish(fill=(1,0,0), color=None, fill_opacity=0.3)

	# ページに反映
	text1_shape.commit()

	# pdf1側のファイル名
	pix1 = page1.get_pixmap()


	# キャンバスを作る
	text2_shape = page2.new_shape()

	# 画像の差異をキャンバスに描く
	for bbox in added_bboxes:
		text2_shape.draw_rect(bbox)

	# キャンバスに描いた図形に色や線のスタイルを適用して描画を確定させる
	text2_shape.finish(fill=(1,0,0), color=None, fill_opacity=0.3)

	# ページに反映
	text2_shape.commit()

	# pdf2側のファイル名
	pix2 = page2.get_pixmap()


	# 左右に連結する処理
	width = pix1.width + pix2.width
	height = max(pix1.height, pix2.height)

	# 新しい空のPixmapを作成（背景を黒にするため alpha=False, colorspace=RGB）
	combined_pix = fitz.Pixmap(fitz.csRGB, (0, 0, width, height), False)
	combined_pix.clear_with(0) # 背景を黒で初期化

	# pix1を左上に配置
	# set_origin で pix1 の内部座標を (0, 0) にリセットしてからコピー
	pix1.set_origin(0, 0)
	combined_pix.copy(pix1, (0, 0, pix1.width, pix1.height))

	# pix2を右上に配置
	# pix2 の内部座標を「貼り付けたい先の開始座標」にセットする
	pix2.set_origin(pix1.width, 0)
	combined_pix.copy(pix2, (pix1.width, 0, pix1.width + pix2.width, pix2.height))

	# 保存
	combined_pix.save(f"{output_dir}/diff_page_{page_no+1:03}.png")

	return


# ---------------------------------------------------------
# 比較メイン処理
# 
# 引数
#	pdf1_path  : 比較pdfファイル1のパス
#	pdf2_path  : 比較pdfファイル2のパス
#	output_dir : 差分結果出力先ディレクトリ
# 戻り値
#	なし
# ---------------------------------------------------------
def compare_pdfs(pdf1_path, pdf2_path, output_dir):
	with fitz.open(pdf1_path) as doc1, fitz.open(pdf2_path) as doc2:
		# 比較対象ページの抽出
		if settings.TARGET_PAGE != "":
			target_page = parse_page_range(settings.TARGET_PAGE)
			target_page = [i - 1 for i in target_page]
		else:
			# ページ数が大きい方を採用
			target_page = tuple(range(0, max(len(doc1), len(doc2))))

		# ページ数分繰り返す
		for i in target_page:
			line_diffs = image_diffs = []

			if i >= len(doc1) or i >= len(doc2):
				print(f"{i+1:3} : SKIP (No page)")
				continue

			# --------------
			# テキスト比較
			# --------------
			text_removed = text_added = []
			if "text" in settings.COMPARISON_TYPE:
				text_removed, text_added = diff_char.compare(doc1[i], doc2[i])

			# --------------
			# 画像比較
			# --------------
			image_removed = image_added = []
			if "image" in settings.COMPARISON_TYPE:
				image_removed, image_added = diff_image.compare(doc1[i], doc2[i])

			# テキスト比較結果と画像比較結果を結合
			removed = text_removed + image_removed
			added = text_added + image_added

			# 結果の出力
			if len(added) + len(removed):
				print(f"{i+1:3} : DIFF --> {output_dir}/diff_page_{i+1:03}.png")
				output_diff(i, doc1[i], doc2[i], added, removed, output_dir)
			else:
				print(f"{i+1:3} : OK")

	return

# ---------------------------------------------------------
# 引数で指定されたページ範囲の文字列を解析してページ番号リストを返す
# 例えば、"2,4,6-8"が指定された場合は、[2,4,6,7,8]を返す
# 
# 引数
#	page_range_str : 比較対象ページ
# 戻り値
#	pages : ページ番号リスト
# ---------------------------------------------------------
def parse_page_range(page_range_str):
	pages = set()
	parts = page_range_str.split(",")

	for part in parts:
		if "-" in part:
			start, end = part.split("-")
			pages.update(range(int(start), int(end) + 1))
		else:
			pages.add(int(part))

	return sorted(pages)

# ---------------------------------------------------------
# メイン
# ---------------------------------------------------------
if __name__ == "__main__":
	if len(sys.argv) < 3:
		print('Arguments are too short')
		exit()

	# 設定を読み込み
	settings.read()

	# 出力ディレクトリ作成
	os.makedirs("output", exist_ok=True)

	# 比較
	compare_pdfs(sys.argv[1], sys.argv[2], "output")

