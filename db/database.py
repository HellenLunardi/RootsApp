import sqlite3

conexao = sqlite3.connect("db/roots.db")
cursor = conexao.cursor()

# Tabela de livros 
cursor.execute("""
CREATE TABLE IF NOT EXISTS livros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    autor TEXT,
    qtde_paginas INTEGER,
    status TEXT CHECK(status IN ('Lendo', 'Concluído', 'Quero ler')),
    pagina_atual INTEGER,
    nota INTEGER,
    genero_id INTEGER,
    FOREIGN KEY (genero_id) REFERENCES generos(id)
)
""")

# Tabela de gêneros
cursor.execute("""
CREATE TABLE IF NOT EXISTS generos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL UNIQUE
)
""")

# Tabela para o progresso de leitura diário 
cursor.execute("""
CREATE TABLE IF NOT EXISTS progresso_diario (
    livro_id INTEGER,
    data TEXT,
    paginas_lidas INTEGER,
    FOREIGN KEY (livro_id) REFERENCES livros(id)
)
""")

# Tabelade anotações
cursor.execute("""
CREATE TABLE IF NOT EXISTS anotacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro_id INTEGER,
    texto TEXT,
    FOREIGN KEY (livro_id) REFERENCES liros(id)
)
""")

conexao.commit()