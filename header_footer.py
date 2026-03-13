import sys
import fitz
import tkinter as tk
import settings
from tkinter import messagebox
from PIL import Image, ImageTk	# 外部ライブラリ

#######################################*
# 変数定義
#######################################*
header_y = 0	# ヘッダーの終了Y座標
footer_y = 0	# フッターの開始Y座標


class HeaderFooter():
	def __init__(self, pix):
		self.click_count = 0

		# PIL Imageへ変換し、さらにTkinter用に変換
		img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

		self.root = tk.Tk()
		self.root.title('ヘッダーの終了位置をクリックしてください')

		# tkinterウィンドウを常に最前面に表示
		self.root.attributes("-topmost", True)

		# tkinterで表示できるように画像変換
		img_tk = ImageTk.PhotoImage(img)

		# Canvasウィジェットの描画
		self.canvas1 = tk.Canvas(self.root, bg="black", width=img.width, height=img.height)

		# Canvasウィジェットに取得した画像を描画
		self.canvas1.create_image(0, 0, image= img_tk, anchor=tk.NW)

		# Canvasウィジェットを配置し、各種イベントを設定
		self.canvas1.pack()
		self.canvas1.bind("<ButtonPress-1>", self.start_point_get)

		self.root.mainloop()


	#######################################*
	# クリックした時のイベント
	#######################################*
	def start_point_get(self, event):
		global header_y, footer_y

		# 1回目:ヘッダーの終了Y座標、2回目:フッターの開始Y座標
		if self.click_count == 0:
			header_y = int(event.y)
			tag_name = 'header'
		else:
			footer_y = int(event.y)
			tag_name = 'footer'

		# canvas1上に横線を描画
		self.canvas1.create_line(0, event.y, self.canvas1.winfo_width(), event.y, fill="red", width=2, tag=tag_name)

		# クリック数+1
		self.click_count += 1

		if self.click_count == 2:
			if header_y > footer_y:
				messagebox.showinfo("警告", "ヘッダーがフッターよりも下に位置しています。\nやり直してください。")
			else:
				msg = 'ヘッダー終了Y座標：' + str(header_y) + '\nフッター開始Y座標：' + str(footer_y) + '\n\nこの位置でよろしいですか？'
				result = messagebox.askyesno('確認', msg)
				if result:
					self.root.destroy()
					return

			# ヘッダーとフッターの線を削除
			self.canvas1.delete("header")
			self.canvas1.delete("footer")
			header_y = footer_y = 0
			self.click_count = 0


# ---------------------------------------------------------
# 数字か判定
# 
# 引数
#	value : 判定文字列
# 戻り値
#	0 : 数字でない
#	1 : 数字
# ---------------------------------------------------------
def is_number(value):
	try:
		int(value)
		return True
	except (ValueError, TypeError):
		return False


# ---------------------------------------------------------
# メイン
# ---------------------------------------------------------
if __name__ == "__main__":
	# 引数の数チェック
	if len(sys.argv) < 2:
		print('Arguments are too short')
		exit()

	# ページ番号の入力
	page_no = input("どのページをもとに設定を行いますか: ")
	page_no = int(page_no) if is_number(page_no) else 0

	# PDFドキュメントを開く
	with fitz.open(sys.argv[1]) as doc:
		if page_no > len(doc):
			print("指定のページは存在しません。")
			exit()

		# ページの高さを取得
		page_height = int(doc[page_no].rect.height)

		# pdfからピックマップを生成
		pix = doc[page_no].get_pixmap()
		if pix.n >= 4:
			pix = fitx.Pixmap(fitz.csRGB, pix)

	# ヘッダーとフッター位置を指定
	HeaderFooter(pix)

	# ヘッダーとフッター位置が指定されたら
	if header_y and footer_y:
		result = messagebox.askyesno('確認', 'settings.json に反映しますか？')
		if result:
			# jsonファイルを読み込む
			settings.write((("common", "header_height", header_y), ("common", "footer_height", page_height - footer_y)))

