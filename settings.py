import json

# ---------------------------------------------------------
# 設定値をjsonファイルに書き込む
# 
# 引数
#	write_data : リスト形式の書き込みデータ
# 戻り値
#	なし
# ---------------------------------------------------------
def write(write_data, setting_file_path="./settings.json"):
	# jsonファイルを読み込む
	with open(setting_file_path, "r", encoding="utf-8") as f:
		data = json.load(f)

	for v in write_data:
		section, key, value = v
		data[section][key] = value
		print(f"[{section}][{key}] = {value}")

	# jsonファイルに書き込む
	with open(setting_file_path, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent=4)


# ---------------------------------------------------------
# 設定値をグローバル変数として取り込む
# 
# 引数
#	setting_file_path : settings.jsonのファイルパス
# 戻り値
#	なし
# ---------------------------------------------------------
def read(setting_file_path="./settings.json"):

	with open(setting_file_path, "r", encoding="utf-8") as f:
		settings = json.load(f)

		print("[ common settings ]")
		for key, value in settings["common"].items():
			globals()[key.upper()] = value
			print(f"  {key.upper():16} = {value}")

		if "text" in COMPARISON_TYPE:
			print("[ text compare settings ]")
			for key, value in settings["text"].items():
				globals()[key.upper()] = value
				print(f"  {key.upper():16} = {value}")

		if "image" in COMPARISON_TYPE:
			print("[ image compare settings ]")
			for key, value in settings["image"].items():
				globals()[key.upper()] = value
				print(f"  {key.upper():16} = {value}")

	print("")
