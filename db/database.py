import sqlite3

conexao = sqlite3.connect("db/roots.db")
cursor = conexao.cursor()

# Tabela de usuários
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    senha TEXT NOT NULL
)
""")

# Tabela de livros
cursor.execute("""
CREATE TABLE IF NOT EXISTS livros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    autor TEXT,
    qtde_paginas INTEGER
)
""")

# Tabela de gêneros de livros
cursor.execute("""
CREATE TABLE IF NOT EXISTS generos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL UNIQUE
)
""")

# Tabela de progresso (relacionamento entre usuário e livro)
cursor.execute("""
CREATE TABLE IF NOT EXISTS progresso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    livro_id INTEGER,
    status TEXT CHECK(status IN ('Lendo', 'Concluído', 'Quero ler')),
    pagina_atual INTEGER, 
    comentario TEXT,
    nota INTEGER,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    FOREIGN KEY (livro_id) REFERENCES livros(id)
)
""")

# Tabela de relacionamento entre livros e gêneros
cursor.execute("""
CREATE TABLE IF NOT EXISTS genero_livros (
    livro_id INTEGER,
    genero_id INTEGER,
    FOREIGN KEY (livro_id) REFERENCES livros(id),
    FOREIGN KEY (genero_id) REFERENCES generos(id),
    PRIMARY KEY (livro_id, genero_id)
)
""")

# Tabela de anotações 
# Permite múltiplas anotações por usuário para o mesmo livro.
cursor.execute("""
CREATE TABLE IF NOT EXISTS anotacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    livro_id INTEGER,
    texto TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    FOREIGN KEY (livro_id) REFERENCES livros(id)
)
""")

conexao.commit()