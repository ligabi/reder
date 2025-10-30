# Archivo: initialize_db.py

from app import app, db, Usuario, Zona 
import os
import sys

print("Iniciando la inicialización de la base de datos...")

# Ejecuta la inicialización de la base de datos dentro del contexto de la aplicación
with app.app_context():
    
    # Crea las tablas en la Base de Datos
    db.create_all()
    
    # Lógica: Crear el usuario administrador (9898) si no existe
    # Esta lógica es la misma que ya tienes en app.py, pero la ejecutamos aquí para Render
    if not Usuario.query.filter_by(numero_acceso='9898').first():
        admin_user = Usuario(
            nombre_completo='ADMINISTRADOR',
            numero_acceso='9898',
            rol='admin'
        )
        db.session.add(admin_user)
        print("✅ Usuario Administrador inicial (9898) creado.")

    # Lógica Opcional: Crear una zona inicial si no existe
    if not Zona.query.filter_by(nombre='Oficina Central').first():
        nueva_zona = Zona(nombre='Oficina Central')
        db.session.add(nueva_zona)
        print("✅ Zona 'Oficina Central' creada.")
    
    db.session.commit()
    print("✅ Base de datos inicializada y tablas creadas.")

print("Finalizado.")
