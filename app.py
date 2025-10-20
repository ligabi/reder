import os
from flask import (
    Flask, 
    render_template, 
    request, 
    redirect, 
    url_for, 
    session, 
    abort, 
    g,
    send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from pathlib import Path
from werkzeug.utils import secure_filename 

# --- Configuración de Archivos y Aplicación Flask ---

PROJECT_ROOT = Path(__file__).parent
app = Flask(__name__, instance_path=str(PROJECT_ROOT / 'instance')) 

# Configuración de Archivos
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configuración de Flask y SQLAlchemy
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una_clave_secreta_fuerte_y_larga_por_defecto_NO_USAR_EN_PRODUCCION') 
# *** MODIFICACIÓN CLAVE PARA RENDER/POSTGRESQL ***
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///tickets.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Funciones Auxiliares de Archivos ---

def allowed_file(filename):
    """Verifica si la extensión del archivo está permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Modelos de la Base de Datos (SQLAlchemy) ---

# NUEVO MODELO: Zona
class Zona(db.Model):
    __tablename__ = 'zona'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    tickets = db.relationship('Ticket', backref='zona', lazy=True)

class Usuario(db.Model):
    """Representa a un Usuario del sistema (Mantenimiento)."""
    __tablename__ = 'usuario' 
    
    id = db.Column(db.Integer, primary_key=True)
    numero_acceso = db.Column(db.String(4), unique=True, nullable=False) 
    nombre_completo = db.Column(db.String(100), nullable=True, default='Mantenimiento') 
    rol = db.Column(db.String(10), default='user')
    tickets = db.relationship('Ticket', backref='creador', lazy=True)

class Ticket(db.Model):
    """Representa una incidencia reportada."""
    __tablename__ = 'ticket'
    
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), default='Abierto') 
    fecha_creacion = db.Column(db.DateTime, default=db.func.now())
    creador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False) 
    comentarios = db.relationship('Comentario', backref='ticket', lazy=True, order_by="Comentario.fecha_creacion")
    
    reference_number = db.Column(db.String(4), nullable=True) 
    photo_path = db.Column(db.String(255), nullable=True)     
    
    # NUEVO CAMPO: Clave Foránea a Zona
    zona_id = db.Column(db.Integer, db.ForeignKey('zona.id'), nullable=True) 

class Comentario(db.Model):
    """Representa la realimentación en un ticket."""
    __tablename__ = 'comentario'
    
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=db.func.now())
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    usuario_id = db.Column(db.String(20), nullable=False) 
    usuario_acceso = db.Column(db.String(4), nullable=False) 

# --- Lógica de Autenticación y Carga de Usuario (sin cambios) ---

@app.before_request
def load_logged_in_user():
    g.user_id = session.get('user_id')
    g.rol = session.get('rol')
    g.numero_acceso = session.get('numero_acceso')
    if g.user_id and g.rol == 'user':
        try:
            user_db_id = int(g.user_id)
            usuario = Usuario.query.get(user_db_id)
            g.nombre_completo = usuario.nombre_completo if usuario else 'Usuario Desconocido'
        except (ValueError, TypeError):
            g.nombre_completo = 'Usuario Desconocido'
    elif g.rol == 'admin':
        g.nombre_completo = 'ADMINISTRADOR'
    else:
        g.nombre_completo = None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user_id is None:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.rol != 'admin':
            abort(403) 
        return f(*args, **kwargs)
    return decorated_function

# --- Rutas de Autenticación y Navegación (sin cambios) ---

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user_id:
        return redirect(url_for('panel_inicio'))
        
    if request.method == 'POST':
        codigo = request.form.get('codigo_acceso', '').strip()
        
        if not codigo:
            return render_template('login.html', error="El código de acceso no puede estar vacío.")

        if codigo == '9898':
            session['user_id'] = 'ADMIN_ID' 
            session['rol'] = 'admin'
            session['numero_acceso'] = '9898'
            return redirect(url_for('panel_admin'))
        
        elif len(codigo) == 4 and codigo.isdigit():
            usuario = Usuario.query.filter_by(numero_acceso=codigo).first()
            if usuario:
                session['user_id'] = str(usuario.id) 
                session['rol'] = 'user'
                session['numero_acceso'] = codigo
                return redirect(url_for('panel_usuario'))
            else:
                return render_template('login.html', error="Usuario no registrado.")
        
        return render_template('login.html', error="Código de acceso inválido.")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/panel')
@login_required
def panel_inicio():
    if g.rol == 'admin':
        return redirect(url_for('panel_admin'))
    elif g.rol == 'user':
        return redirect(url_for('panel_usuario'))
    else:
        return redirect(url_for('logout'))

# --- Rutas de Usuario (MODIFICADA) ---

@app.route('/mis_tickets')
@login_required
def panel_usuario():
    """Vista del usuario: solo sus tickets y formulario para crear uno nuevo, con capacidad de búsqueda."""
    if g.rol != 'user':
        return redirect(url_for('panel_admin')) 

    try:
        user_db_id = int(g.user_id)
    except ValueError:
        abort(403) 
    
    # 1. Base query: solo tickets creados por el usuario actual
    query = Ticket.query.filter_by(creador_id=user_db_id).order_by(Ticket.fecha_creacion.desc())
    
    # 2. Búsqueda por número de referencia
    search_ref = request.args.get('search_ref', '').strip()
    
    if search_ref:
        # Busca cualquier ticket cuyo número de referencia contenga el texto (LIKE)
        query = query.filter(Ticket.reference_number.like(f'%{search_ref}%'))
        
    tickets = query.all()
    
    # NUEVO: Obtener todas las zonas para el formulario
    zonas = Zona.query.order_by(Zona.nombre).all()
    
    return render_template('panel_usuario.html', tickets=tickets, search_ref=search_ref, zonas=zonas)

@app.route('/ticket/crear', methods=['POST'])
@login_required
def crear_ticket():
    if g.rol != 'user':
         return "Solo los usuarios (4 dígitos) pueden crear tickets.", 403

    titulo = request.form.get('titulo', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    zona_id = request.form.get('zona_id') # NUEVO: Obtener el ID de la zona
    
    if not titulo or not descripcion:
        return "Título y Descripción son requeridos.", 400

    try:
        creador_id_int = int(g.user_id)
    except ValueError:
        return "Error de ID de creador.", 500

    photo_path = None
    if 'photo' in request.files:
        file = request.files['photo']
        if file.filename != '' and allowed_file(file.filename):
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
                
            filename = secure_filename(file.filename)
            # Utilizar el timestamp para asegurar la unicidad del nombre
            import time
            unique_filename = f"{int(time.time())}_{filename}" 
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            photo_path = unique_filename 

    # Determinar zona_id. Si es '0' o vacío, se guarda como None.
    zona_to_save = int(zona_id) if zona_id and zona_id.isdigit() and int(zona_id) != 0 else None
    
    nuevo_ticket = Ticket(
        titulo=titulo, 
        descripcion=descripcion, 
        creador_id=creador_id_int,
        estado='Abierto',
        photo_path=photo_path,
        zona_id=zona_to_save # NUEVO: Guardar la zona
    )
    db.session.add(nuevo_ticket)
    db.session.commit()
    
    # Asignar reference_number después del commit para usar el ID del ticket
    nuevo_ticket.reference_number = str(nuevo_ticket.id).zfill(4)
    db.session.commit()

    return redirect(url_for('panel_usuario'))
    
# --- Rutas de Administrador (MODIFICADA) ---

@app.route('/admin')
@admin_required
def panel_admin():
    """Vista del Administrador: ver todos los tickets, gestión de usuarios, conteo y búsqueda."""
    
    # 1. Base query para todos los tickets
    query = Ticket.query.order_by(Ticket.fecha_creacion.desc())
    
    # 2. Parámetros de búsqueda
    search_ref = request.args.get('search_ref', '').strip()
    search_user = request.args.get('search_user', '').strip()
    
    if search_ref:
        query = query.filter(Ticket.reference_number.like(f'%{search_ref}%'))
    
    if search_user:
        # Busca al usuario por su número de acceso
        user = Usuario.query.filter_by(numero_acceso=search_user).first()
        if user:
            query = query.filter(Ticket.creador_id == user.id)
        else:
            # Si el usuario no existe, la búsqueda retorna vacío
            query = query.filter(Ticket.creador_id == -1) 
            
    tickets = query.all()
    usuarios = Usuario.query.filter_by(rol='user').all() 
    # NUEVO: Obtener todas las zonas para la gestión y visualización
    zonas = Zona.query.order_by(Zona.nombre).all()

    # 3. Conteo de tickets por estado para el resumen (calculado sobre TODOS los tickets)
    status_counts = db.session.query(
        Ticket.estado, db.func.count(Ticket.id)
    ).group_by(Ticket.estado).all()
    
    counts = {s[0]: s[1] for s in status_counts}
    
    # Asegura que todos los estados aparezcan, incluso si el conteo es 0
    full_counts = {
        'Abierto': counts.get('Abierto', 0),
        'En Progreso': counts.get('En Progreso', 0),
        'Resuelto': counts.get('Resuelto', 0),
        'Rechazado': counts.get('Rechazado', 0)
    }

    return render_template('panel_admin.html', 
                           tickets=tickets, 
                           usuarios=usuarios, 
                           status_counts=full_counts,
                           search_ref=search_ref, 
                           search_user=search_user,
                           zonas=zonas # NUEVO: Pasar zonas
                          )

# NUEVA RUTA: Gestión de Zonas (Creación y Eliminación)
@app.route('/admin/zonas', methods=['POST'])
@admin_required
def gestionar_zonas():
    # 1. Crear nueva zona
    nombre_zona = request.form.get('nombre_zona', '').strip()
    if nombre_zona:
        if not Zona.query.filter_by(nombre=nombre_zona).first():
            nueva_zona = Zona(nombre=nombre_zona)
            db.session.add(nueva_zona)
            db.session.commit()
        return redirect(url_for('panel_admin'))
    
    # 2. Eliminar zona
    zona_id_a_eliminar = request.form.get('eliminar_zona_id')
    if zona_id_a_eliminar and zona_id_a_eliminar.isdigit():
        zona = Zona.query.get(int(zona_id_a_eliminar))
        if zona:
            # Reasignar tickets a NULL antes de eliminar la zona para evitar errores de FK
            # Nota: Usamos 'zona_id': None en un diccionario para la función update()
            Ticket.query.filter_by(zona_id=zona.id).update({'zona_id': None}, synchronize_session=False)
            db.session.delete(zona)
            db.session.commit()
        return redirect(url_for('panel_admin'))

    return redirect(url_for('panel_admin'))

@app.route('/admin/usuario/crear', methods=['POST'])
@admin_required
def crear_usuario():
    # ... (Lógica de creación de usuario, sin cambios) ...
    numero_acceso = request.form.get('numero_acceso', '').strip()
    nombre_completo = request.form.get('nombre_completo', '').strip()
    
    if len(numero_acceso) != 4 or not numero_acceso.isdigit():
        return "El número debe ser de 4 dígitos y solo números.", 400
        
    if not nombre_completo:
        return "El nombre completo es requerido.", 400

    if Usuario.query.filter_by(numero_acceso=numero_acceso).first():
        return f"El usuario {numero_acceso} ya existe.", 409
        
    nuevo_usuario = Usuario(numero_acceso=numero_acceso, nombre_completo=nombre_completo, rol='user')
    db.session.add(nuevo_usuario)
    db.session.commit()
    return redirect(url_for('panel_admin'))

@app.route('/admin/ticket/modificar/<int:ticket_id>', methods=['POST'])
@admin_required
def modificar_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    
    nuevo_estado = request.form.get('estado')
    nueva_descripcion = request.form.get('descripcion')
    nueva_referencia = request.form.get('reference_number', '').strip()
    zona_id = request.form.get('zona_id') # NUEVO: Obtener el ID de la zona
    
    estados_permitidos = ['Abierto', 'En Progreso', 'Resuelto', 'Rechazado']
    
    if nuevo_estado and nuevo_estado in estados_permitidos:
        ticket.estado = nuevo_estado
    
    if nueva_descripcion:
        ticket.descripcion = nueva_descripcion
        
    if nueva_referencia and len(nueva_referencia) <= 4 and nueva_referencia.isalnum(): 
        ticket.reference_number = nueva_referencia
        
    # NUEVO: Actualizar Zona
    if zona_id is not None and zona_id.isdigit():
        zona_to_save = int(zona_id)
        if zona_to_save == 0:
            ticket.zona_id = None
        else:
            ticket.zona_id = zona_to_save
    
    db.session.commit()
    return redirect(url_for('ver_ticket', ticket_id=ticket_id))

# --- Rutas de Detalle y Archivos (MODIFICADA) ---

@app.route('/ticket/<int:ticket_id>')
@login_required
def ver_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    
    if g.rol == 'user' and str(ticket.creador_id) != g.user_id:
        abort(403) 
        
    comentarios = ticket.comentarios 
    
    creador = Usuario.query.get(ticket.creador_id)
    
    creador_nombre = creador.nombre_completo if creador else 'Desconocido'
    creador_acceso = creador.numero_acceso if creador else 'N/A' 
    
    puede_comentar = (g.rol == 'admin') or (g.rol == 'user' and str(ticket.creador_id) == g.user_id)
    
    # NUEVO: Obtener todas las zonas para el formulario de edición del Admin
    zonas = Zona.query.order_by(Zona.nombre).all()
    
    return render_template('ver_ticket.html', 
        ticket=ticket, 
        comentarios=comentarios, 
        creador_nombre=creador_nombre,
        creador_acceso=creador_acceso,
        puede_comentar=puede_comentar,
        zonas=zonas # NUEVO: Pasar zonas al template
    )

@app.route('/ticket/<int:ticket_id>/comentar', methods=['POST'])
@login_required
def comentar_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    texto = request.form.get('texto', '').strip()
    
    if not texto:
        return "El comentario no puede estar vacío.", 400

    # Corregir lógica de control de acceso para comentar
    if g.rol == 'user' and str(ticket.creador_id) != g.user_id: 
        abort(403) 

    nuevo_comentario = Comentario(
        texto=texto,
        ticket_id=ticket_id,
        usuario_id=g.user_id, 
        usuario_acceso=g.numero_acceso
    )
    db.session.add(nuevo_comentario)
    db.session.commit()
    return redirect(url_for('ver_ticket', ticket_id=ticket_id))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Inicialización y Ejecución ---

def init_db():
    with app.app_context(): 
        # Esta línea crea la carpeta 'uploads' si no existe
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
             os.makedirs(app.config['UPLOAD_FOLDER'])
        # Esta línea crea las tablas en la Base de Datos
        db.create_all()
        print("Base de datos inicializada y tablas creadas.")

if __name__ == '__main__':
    init_db() 
    app.run(debug=True, host='0.0.0.0')