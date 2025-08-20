import requests
import sqlite3

def search_books(query):
    api_url: f"https://www.googleapis.com/books/v1/volumes?q={query}"

    response = requests.get(api_url)
    if response.status_code == 200:
        return response.json().get('items', [])
    return []