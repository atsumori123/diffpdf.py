Command

	> diffpdf.py <filepath1> <filepath2> 

	filepath1:
		比較するpdfファイルのパス

	filepath2:
		比較するpdfファイルのパス


settings.json
	common settings
		comparison_type:
			比較するモードの指定
			"text"			行単位のテキスト比較
			"image"			画像比較
			"text,image"	行単位のテキストと画像の両方で比較

		header_height:
			ヘッダー領域の高さ (px)

		footer_height:
			フッター領域の高さ (px)

	text settings
		ignore_case:
			大文字、小文字を区別しない

	image settings
		valid_area_size:
			差異の面積がこのサイズよりも小さい場合は差異と見なさない

