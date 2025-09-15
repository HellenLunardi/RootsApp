# 🌱 Roots – App de Leitura

O **Roots** é um aplicativo desenvolvido em **Python + KivyMD** para ajudar leitores a acompanhar seu progresso de leitura de forma simples e intuitiva.  
Ele combina um **cronômetro de leitura**, **gráficos semanais** e **armazenamento local em SQLite**, permitindo que você acompanhe seu hábito de leitura ao longo do tempo.

---

## 📸 Funcionalidades

- ⏱️ **Cronômetro de leitura**
  - Iniciar, pausar, retomar e zerar o tempo.
  - Salvar sessões de leitura no banco de dados.

- 📊 **Gráficos semanais**
  - Visualização do tempo de leitura de **domingo a sábado**.
  - Linha da **média de minutos/dia** destacada.
  - Estatísticas de total, dia mais produtivo e dia menos produtivo.

- 💾 **Banco de dados local (SQLite)**
  - Armazena sessões de leitura em `roots.db`.
  - Cada sessão contém início, fim, duração e data.

- 🎨 **Interface moderna**
  - Feita com **KivyMD**.
  - Layout responsivo, otimizado para desktop e mobile.

---

## 🛠️ Tecnologias usadas

- [Python 3.10+](https://www.python.org/)
- [Kivy](https://kivy.org/#home)
- [KivyMD](https://kivymd.readthedocs.io/en/latest/)
- [SQLite3](https://www.sqlite.org/index.html)
