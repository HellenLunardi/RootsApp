import requests
import sqlite3
import os.path

from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty, NumericProperty

from kivymd.uix.boxlayout import MDBoxLayout
from kivy.uix.image import AsyncImage

class BookItem(MDBoxLayout):
    title = StringProperty('')
    cover_url = StringProperty('')
    book_id = StringProperty('')
    authors = StringProperty('')
    page_count = NumericProperty(0)

class MainScreen(Screen):
    pass

class RootsApp(MDApp):
    def build(self):
        # Chama a funçao para inicializar o banco de dados
        self.initialize_database()
        return Builder.load_file("roots.kv")
    
    def add_book_search(self, query):
        """
        Cria as tabelas de livros, generos, progresso_diario e anotaçoes se elas nao existirem
        """
        if not os.path.exists("db"):
            os.makedirs("db")
        conn = sqlite3.connect('db/roots.db')
        cursor = conn.cursor()
        """
        Busca livros na API e adiciona widgets na grade.
        Recebe o texto do campo de pesquisa como argumento.
        """
        api_url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
        response = requests.get(api_url)

        books_grid = self.root.get_screen('main_screen').ids.books_grid
        books_grid.clear_widgets() # limpa a grade antes de adicionar o novo livro


        if response.status_code == 200:
            books_data = response.json().get('items', [])

            for item in books_data:
                volume_info = item.get('volumeInfo', {})

                # Coleta todas as informações necessárias do livro
                book_id = item.get('id', '')
                title = volume_info.get('title', 'Título Desconhecido')
                authors_list = volume_info.get('authors', ['Autor Desconhecido'])
                authors = ', '.join(authors_list)
                cover_url = volume_info.get('imageLinks', {}).get('thumbnail', '')
                page_count = volume_info.get('pageCount', 0)

                # Cria uma instancia do widget BookItem com as infos corretas
                book_widget = BookItem(
                    book_id=book_id,
                    title=title,
                    authors=authors,
                    cover_url=cover_url,
                    page_count=page_count
                )

                books_grid.add_widget(book_widget)
        else:
            print("Erro na busca da API")


if __name__ == "__main__":
    RootsApp().run()