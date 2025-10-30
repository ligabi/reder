# app.py

import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash # Importado por si lo usas
import random
import string

# Inicialización de la aplicación
app = Flask(__name__)
# ⚠️ IMPORTANTE: Define una variable de entorno 'SECRET_KEY' en Render
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'clave_de_desarrollo_temporal_9876') 

# -------------------------------------------------------------
# 💾 CONFIGURACIÓN CRÍTICA DE LA BASE DE DATOS (POSTGRES PERSISTENTE)
# -------------------------------------------------------------

# Leer la URL de conexión de la base de datos de la variable de entorno
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # 🚨 SOLUCIÓN DE PERSISTENCIA: Ajuste de prefijo para compatibilidad con SQLAlchemy.
    # Render usa 'postgres://', pero SQLAlchemy requiere 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    print("✅ Configurado para usar PostgreSQL persistente.")
else:
    # Fallback para desarrollo local (¡No persistente en Render!)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///local_db_temp.sqlite' 
    print("⚠️ ADVERTENCIA: Usando SQLite local. Define DATABASE_URL en Render.")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------------------------------------------------------------
# Definición de Modelos
# -------------------------------------------------------------

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_completo = db.Column(db.String(100), nullable=False)
    numero_acceso = db.Column(db.String(4), unique=True, nullable=False)
    rol = db.Column(db.String(20), default='usuario') # 'usuario', 'admin', 'tecnico'
    tickets_creados = db.relationship('Ticket', backref='creador', lazy=True)

class Zona(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    tickets = db.relationship('Ticket', backref='zona', lazy=True)
    
class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(50), default='Abierto') # Abierto, En Proceso, Cerrado, etc.
    reference_number = db.Column(db.String(4), unique=True, nullable=True)
    motivo_rechazo = db.Column(db.Text, nullable=True)
    acusado_por_usuario = db.Column(db.Boolean, default=False)
    
    # Relaciones
    creador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    zona_id = db.Column(db.Integer, db.ForeignKey('zona.id'), nullable=True)
    
    # Función para generar la referencia
    @staticmethod
    def generate_ref_number():
        while True:
            # Genera un número de 4 dígitos (ej: 0045)
            ref = ''.join(random.choices(string.digits, k=4))
            if not Ticket.query.filter_by(reference_number=ref).first():
                return ref

# -------------------------------------------------------------
# Decoradores y Hooks
# -------------------------------------------------------------

# Carga el usuario de la sesión antes de cada petición
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = db.session.get(Usuario, user_id)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash('Debes iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------
# Rutas Mínimas (Asegura que incluyas el resto de tus rutas aquí)
# -------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        nombre = request.form.get('nombre_acceso')
        codigo = request.form.get('codigo_acceso')

        user = Usuario.query.filter_by(numero_acceso=codigo).first()

        if user and user.nombre_completo.upper() == nombre.upper():
            session.clear()
            session['user_id'] = user.id
            flash(f'Bienvenido, {user.nombre_completo}.', 'success')
            return redirect(url_for('panel_inicio'))
        else:
            error = 'Credenciales inválidas. Por favor, verifica tu nombre y código de acceso.'
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('login'))

@app.route('/panel')
@login_required
def panel_inicio():
    zonas = Zona.query.all()
    if g.user.rol == 'admin' or g.user.rol == 'tecnico':
        # Los administradores ven todos los tickets
        tickets = Ticket.query.order_by(Ticket.fecha_creacion.desc()).all()
        # Se asume que panel_admin.html usa la variable 'active_tab'
        return render_template('panel_admin.html', active_tab='tickets', tickets=tickets, zonas=zonas)
    else:
        # Los usuarios ven solo sus tickets (se asume que hay otra ruta/funcionalidad para ver la lista)
        tickets_usuario = Ticket.query.filter_by(creador_id=g.user.id).order_by(Ticket.fecha_creacion.desc()).all()
        # Esto redirige a la vista de creación de ticket por defecto
        return render_template('panel_usuario.html', mostrando_lista=False, zonas=zonas, tickets=tickets_usuario)
        
@app.route('/crear_ticket', methods=['POST'])
@login_required
def crear_ticket():
    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion')
    zona_id = request.form.get('zona_id')
    
    try:
        new_ticket = Ticket(
            titulo=titulo,
            descripcion=descripcion,
            creador_id=g.user.id,
            zona_id=int(zona_id) if zona_id and int(zona_id) != 0 else None,
            reference_number=Ticket.generate_ref_number()
        )
        db.session.add(new_ticket)
        db.session.commit()
        flash(f'Ticket creado con éxito. Ref: #{new_ticket.reference_number}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear el ticket: {e}', 'danger')

    return redirect(url_for('panel_inicio'))

# -------------------------------------------------------------
# Punto de Ejecución
# -------------------------------------------------------------

if __name__ == '__main__':
    # Usado para pruebas locales
    app.run(debug=True)
