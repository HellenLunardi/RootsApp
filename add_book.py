import sqlite3
import requests

def add_book():
    api_url = "https://www.googleapis.com/books/v1/volumes"
    resposta = requests.get(api_url)

    if resposta.status_code == 200:
        dados = resposta.json()
        livros = dados.get('items', [])
        
        if not livros:
            print("Nenhum livro encontrado.")
            return
        
        for livro in livros:
            titulo = livro['volumeInfo'].get('title', 'Título desconhecido')
            autores = ', '.join(livro['volumeInfo'].get('authors', ['Autor desconhecido']))
            ano_publicacao = livro['volumeInfo'].get('publishedDate', 'Data desconhecida')
            
            print(f"Título: {titulo}, Autores: {autores}, Ano de Publicação: {ano_publicacao}")