import fitz  # PyMuPDF
import cv2
import numpy as np

# ---------------------------------------------------------
# ページから画像とその情報の取得
#
# 引数
#	page : ページ (PyMuPDF)
# 戻り値
#	data : 画像とその情報のリスト
# ---------------------------------------------------------
def get_images_with_geometry(page):
	# PDFから画像とその配置座標をリストで取得
	image_infos = page.get_image_info()
	
	data = []
	orb = cv2.ORB_create()
	
	for info in image_infos:
		bbox = info['bbox'] # (x0, y0, x1, y1)
		# 画像部分のみをキャプチャ
		pix = page.get_pixmap(clip=bbox, matrix=fitz.Matrix(2, 2))
		img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
		gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
		
		# 特徴量計算
		kp, des = orb.detectAndCompute(gray, None)
		
		data.append({
			"bbox": bbox,
			"center": ((bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2),
			"descriptors": des,
			"matched": False # ペアリング済みフラグ
		})

	return data


# ---------------------------------------------------------
# 2つの画像記述子が『形として同じ』か判定
#
# 引数
#	des1 : 画像特徴量1
#	des2 : 画像特徴量2
# 戻り値
#	0 : 不一致
#	1 : 一致
# ---------------------------------------------------------
# 画像特徴量とは、
#	画像そのものは膨大なピクセルの集まりだが、そのままでは比較が難しいため、
#	次のような“特徴的な点”を抽出して数値化。
#	・角（コーナー）
#	・エッジ（境界線）
#	・模様（テクスチャ）
#	・特徴的な点の周囲の明暗パターン
# ---------------------------------------------------------
def is_same_shape(des1, des2):
	# 特徴量が存在しない場合はFalse
	if des1 is None or des2 is None: return False

	# Brute-Force Matcherで特徴量を照合
	bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
	matches = bf.match(des1, des2)

	# 距離が近い=良い一致だけを抽出
	good_matches = [m for m in matches if m.distance < 35]

	# 良い一致が一定数以上あれば同じ形とみなす
	return len(good_matches) > 15 


# ---------------------------------------------------------
# 位置と形状を考慮して1対1で比較して削除、追加を判定
# 
# 引数
#	old_list : 画像とその情報のリスト
#	new_list : 画像とその情報のリスト
# 戻り値
#	added_bboxes   : 追加された画像のリスト
#	removed_bboxes : 削除された画像のリスト
# ---------------------------------------------------------
def compare_independently(old_list, new_list):
	# old_listの画像を1つずつ処理
	for old_item in old_list:
		# 削除(Removed)の判定: 旧版にあるものが新版でペアリングできるか
		best_match_idx = -1
		min_dist = float('inf')
		
		# new_listの画像を順にチェック
		for i, new_item in enumerate(new_list):
			# 既に使用済みの新画像はスキップ
			if new_item["matched"]: continue
			
			# 形が同じか確認
			if is_same_shape(old_item["descriptors"], new_item["descriptors"]):
				# 中心座標の距離を計算
				# 最も近い位置にあるものを優先（位置ズレ許容のため）
				dist = np.sqrt((old_item["center"][0] - new_item["center"][0])**2 + 
							   (old_item["center"][1] - new_item["center"][1])**2)
				
				# 同じ位置（閾値内）にあれば同一個体とみなす
				if dist < 10 and dist < min_dist: 
					min_dist = dist
					best_match_idx = i
		
		# 同一個体が見つかったら、両方にmatched=Trueを設定
		if best_match_idx != -1:
			old_item["matched"] = True
			new_list[best_match_idx]["matched"] = True

	# 結果の集計
	# 旧版でマッチしなかった→removed
	# 新版でマッチしなかった→added
	removed_bboxes = [item["bbox"] for item in old_list if not item["matched"]]
	added_bboxes = [item["bbox"] for item in new_list if not item["matched"]]
	
	return added_bboxes, removed_bboxes


# ---------------------------------------------------------
# 画像比較メイン処理
# 
# 引数
#	page : ページ (PyMuPDF)
#	page : ページ (PyMuPDF)
# 戻り値
#	added_bboxes   : 追加された画像のリスト
#	removed_bboxes : 削除された画像のリスト
# ---------------------------------------------------------
def compare(page1, page2):
	old_data = get_images_with_geometry(page1)
	new_data = get_images_with_geometry(page2)

	return compare_independently(old_data, new_data)

