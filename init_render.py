# init_render.py
# Este script SÓLO se usará en el Build Command de Render

from app import init_db

print("Iniciando la creación de la base de datos (Build Command)...")

# Llama a la función que crea las tablas y el admin
init_db()

print("Creación de la base de datos completada.")
