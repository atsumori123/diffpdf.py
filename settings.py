import json

# ---------------------------------------------------------
# 設定値をグローバル変数として取り込む
# 
# 引数
#	setting_file_path : settings.jsonのファイルパス
# 戻り値
#	なし
# ---------------------------------------------------------
def load(setting_file_path="./settings.json"):

	with open(setting_file_path, "r") as f:
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
