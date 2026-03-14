import fitz
import difflib
import settings

# ---------------------------------------------------------
# rawdict から文字と bbox を抽出
# 
# 引数
#	page : ページ (PyMuPDF)
# 戻り値
#	merged : ページから抽出した文字 (bbox付き)
# ---------------------------------------------------------
def get_chars(page):
	raw = page.get_text("rawdict")
	chars = []

	# テキストブロック以外は無視する
	for block in raw["blocks"]:
		if block["type"] != 0:	# テキストブロック以外は無視
			continue

		for line in block["lines"]:
			n = 1
			for span in line["spans"]:
				for c in span["chars"]:
					text = c.get("c") if not settings.IGNORE_CASE else c.get("c").lower()
					bbox = c.get("bbox")
					if text and bbox and len(bbox) == 4:
						chars.append((text, bbox))

	return chars


# ---------------------------------------------------------
# difflib による文字単位差分
# 
# 引数
#	char1 : ページから抽出した文字 (bbox付き)
#	char2 : ページから抽出した文字 (bbox付き)
# 戻り値
#	removed : 削除した文字のbboxリスト
#	added   : 追加した文字のbboxリスト
# ---------------------------------------------------------
def diff_chars(chars1, chars2):
	seq1 = [c[0] for c in chars1]
	seq2 = [c[0] for c in chars2]

	diff = difflib.ndiff(seq1, seq2)

	removed = []
	added = []

	idx1 = idx2 = 0

	for d in diff:
		code = d[0]

		if code == "?":
			continue

		if code == "-":
			removed.append(chars1[idx1][1])
			idx1 += 1

		elif code == "+":
			added.append(chars2[idx2][1])
			idx2 += 1

		else:
			idx1 += 1
			idx2 += 1

	return removed, added


# ---------------------------------------------------------
# 近接する bbox を結合する
# 
# 引数
#	char_list	 : 文字リスト
#	x_gap, y_gap : 隣の差異が指定の座標以内であれば結合する
# 戻り値
#	merged : 隣り合う差異を結合させた後の差分リスト
# ---------------------------------------------------------
def merge_bboxes(char_list, x_gap=2, y_gap=2):
	if not char_list:
		return []

	# y座標でソート（行単位でまとめる）
	char_list = sorted(char_list, key=lambda x: (x[1], x[0]))

	merged = []
	current = list(char_list[0])

	for bbox in char_list:
		x0, y0, x1, y1 = bbox

		# 同じ行（y座標が近い）かつ横に近接している場合は結合
		if abs(y0 - current[1]) < y_gap and abs(x0 - current[2]) < x_gap:
			current[2] = x1  # x1 を伸ばす
			current[3] = max(current[3], y1)
		else:
			merged.append(tuple(current))
			current = [x0, y0, x1, y1]

	merged.append(tuple(current))

	return merged


# ---------------------------------------------------------
# ヘッダー・フッター除去
# 
# 引数
#	boxes		: 差異のbboxリスト
#	page_height : ページの高さ
# 戻り値
#	ヘッダー・フッターを除外したbboxリスト
# ---------------------------------------------------------
def remove_header_footer(boxes, page_height):
	filtered = []
	for bbox in boxes:
		x0, y0, x1, y1 = bbox
		if y1 > settings.HEADER_HEIGHT and y0 < (page_height - settings.FOOTER_HEIGHT):
			filtered.append(bbox)
	
	return filtered

# ---------------------------------------------------------
# テキスト比較 (文字単位) メイン処理
# 
# 引数
#	page : ページ (PyMuPDF)
#	page : ページ (PyMuPDF)
# 戻り値
#	removed_bboxes : 削除された画像のリスト
#	added_bboxes   : 追加された画像のリスト
# ---------------------------------------------------------
def compare(page1, page2):
	# ページ内の全ての文字を抽出する
	chars1 = get_chars(page1)
	chars2 = get_chars(page2)

	# 比較
	removed_bboxes, added_bboxes = diff_chars(chars1, chars2)

	# ヘッダーとフッターを除外
	removed_bboxes = remove_header_footer(removed_bboxes, page1.rect.height)
	added_bboxes = remove_header_footer(added_bboxes, page2.rect.height)

	# 隣り合う差分はbboxを結合
	removed_bboxes = merge_bboxes(removed_bboxes)
	added_bboxes = merge_bboxes(added_bboxes)

	return removed_bboxes, added_bboxes


