# Archivo: initialize_db.py
from app import app, db, init_db
import os
import sys

# Script para inicializar las tablas de la base de datos en Render.
# Solo llama a la función init_db() que contiene db.create_all().

print("Iniciando la inicialización de la base de datos...")

# Ejecuta la inicialización de la base de datos dentro del contexto de la aplicación
with app.app_context():
    # Esta línea crea las tablas en la Base de Datos (PostgreSQL en Render)
    # y la carpeta 'uploads'
    db.create_all()
    
    # OPCIONAL: Si deseas pre-cargar zonas por defecto (como las que tenías en SQLite)
    # Aquí es donde podrías agregar la lógica para crear entradas iniciales (usuarios, zonas, etc.)
    # Por ejemplo, para crear la zona "Oficina Principal" si no existe:
    # from app import Zona # Asumiendo que Zona es tu modelo
    # if not Zona.query.filter_by(nombre='Oficina Principal').first():
    #     nueva_zona = Zona(nombre='Oficina Principal')
    #     db.session.add(nueva_zona)
    #     db.session.commit()
    #     print("Zona 'Oficina Principal' creada.")
    
    print("✅ Base de datos inicializada y tablas creadas (incluyendo 'zona').")

print("Finalizado.")
