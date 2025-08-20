import kivy
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen

GUI = Builder.load_file("roots.kv")

class AppRoots(App):
    def build(self):
        return GUI
    
if __name__ == '__main__':
    AppRoots().run()
