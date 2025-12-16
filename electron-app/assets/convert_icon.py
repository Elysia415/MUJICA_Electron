from PIL import Image
import os

img_path = r'c:\Users\26015\Desktop\code\Y3H1\InformationRetrieval\MUJICA\MUJICA_Electron\electron-app\assets\icon.png'
ico_path = r'c:\Users\26015\Desktop\code\Y3H1\InformationRetrieval\MUJICA\MUJICA_Electron\electron-app\assets\icon.ico'

img = Image.open(img_path)
img.save(ico_path, format='ICO', sizes=[(256, 256)])
print(f"Converted {img_path} to {ico_path}")
