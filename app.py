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
    send_from_directory,
    flash
)
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from pathlib import Path
from werkzeug.utils import secure_filename 
from collections import defaultdict 
from datetime import datetime # Importar datetime para el modelo Notificacion

# --- Configuración de Archivos y Aplicación Flask ---

PROJECT_ROOT = Path(__file__).parent
app = Flask(__name__, instance_path=str(PROJECT_ROOT / 'instance')) 

# Configuración de Archivos
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configuración de Flask y SQLAlchemy
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una_clave_secreta_fuerte_y_larga_por_defecto_NO_USAR_EN_PRODUCCION') 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tickets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Funciones Auxiliares de Archivos ---

def allowed_file(filename):
    """Verifica si la extensión del archivo está permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Modelos de la Base de Datos (SQLAlchemy) ---

class Zona(db.Model):
    __tablename__ = 'zona'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    tickets = db.relationship('Ticket', backref='zona', lazy=True)

class Usuario(db.Model):
    __tablename__ = 'usuario' 
    id = db.Column(db.Integer, primary_key=True)
    numero_acceso = db.Column(db.String(4), unique=True, nullable=False) 
    nombre_completo = db.Column(db.String(100), nullable=True, default='Mantenimiento') 
    rol = db.Column(db.String(10), default='user')
    tickets = db.relationship('Ticket', backref='creador', lazy=True)
    notificaciones = db.relationship('Notificacion', backref='receptor', lazy=True) # NUEVO: Relación a Notificaciones

class Ticket(db.Model):
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
    motivo_rechazo = db.Column(db.Text, nullable=True) 
    acusado_por_usuario = db.Column(db.Boolean, default=False) 
    zona_id = db.Column(db.Integer, db.ForeignKey('zona.id'), nullable=True) 

class Comentario(db.Model):
    __tablename__ = 'comentario'
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=db.func.now())
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    usuario_id = db.Column(db.String(20), nullable=False) 
    usuario_acceso = db.Column(db.String(4), nullable=False) 

# --- NUEVO MODELO DE NOTIFICACIONES ---
class Notificacion(db.Model):
    __tablename__ = 'notificacion'
    id = db.Column(db.Integer, primary_key=True)
    # Receptor de la notificación (creador del ticket)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False) 
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    
    tipo = db.Column(db.String(50), nullable=False) # Ej: 'comentario', 'estado_cambiado', 'modificacion'
    mensaje = db.Column(db.String(255), nullable=False)
    leida = db.Column(db.Boolean, default=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow) 
    
    ticket = db.relationship('Ticket', backref='notificaciones')
# -------------------------------------

# --- Función auxiliar para crear notificaciones ---
def crear_notificacion(usuario_id, ticket_id, tipo, mensaje):
    """Crea y añade a la sesión una nueva notificación para el usuario."""
    # Nota: el commit se hará en la función principal
    try:
        notificacion = Notificacion(
            usuario_id=usuario_id, 
            ticket_id=ticket_id, 
            tipo=tipo, 
            mensaje=mensaje
        )
        db.session.add(notificacion)
    except Exception as e:
        print(f"Error al crear notificación: {e}")
# --------------------------------------------------

# --- Lógica de Autenticación y Carga de Usuario (MODIFICADA) ---

@app.before_request
def load_logged_in_user():
    g.user_id = session.get('user_id')
    g.rol = session.get('rol')
    g.numero_acceso = session.get('numero_acceso')
    g.notificaciones_sin_leer_count = 0 # Inicializar contador
    
    if g.user_id and g.rol == 'user':
        try:
            user_db_id = int(g.user_id)
            usuario = Usuario.query.get(user_db_id)
            g.nombre_completo = usuario.nombre_completo if usuario else 'Usuario Desconocido'
            
            # --- NUEVA LÓGICA DE NOTIFICACIONES ---
            g.notificaciones_sin_leer_count = Notificacion.query.filter_by(
                usuario_id=user_db_id, 
                leida=False
            ).count()
            # -------------------------------------
            
        except (ValueError, TypeError):
            g.nombre_completo = 'Usuario Desconocido'
    elif g.rol == 'admin':
        g.nombre_completo = 'ADMINISTRADOR'
    else:
        g.nombre_completo = None

def login_required(f):
# ... (Función sin cambios) ...
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user_id is None:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
# ... (Función sin cambios) ...
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.rol != 'admin':
            abort(403) 
        return f(*args, **kwargs)
    return decorated_function

# --- Rutas de Autenticación y Navegación (Sin cambios) ---

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
# ... (Ruta sin cambios) ...
    if g.user_id:
        return redirect(url_for('panel_inicio'))
        
    if request.method == 'POST':
        nombre = request.form.get('nombre_acceso', '').strip() 
        codigo = request.form.get('codigo_acceso', '').strip()
        
        if not nombre or not codigo:
            return render_template('login.html', error="El nombre de usuario y el código de acceso no pueden estar vacíos.")

        # Lógica para Administrador (9898)
        if codigo == '9898':
            if nombre.upper() != 'ADMINISTRADOR':
                 return render_template('login.html', error="Nombre de usuario y/o código de acceso inválido.")
                 
            session['user_id'] = 'ADMIN_ID' 
            session['rol'] = 'admin'
            session['numero_acceso'] = '9898'
            return redirect(url_for('panel_admin'))
        
        # Lógica para Usuario (4 dígitos)
        elif len(codigo) == 4 and codigo.isdigit():
            usuario = Usuario.query.filter_by(numero_acceso=codigo, nombre_completo=nombre).first()
            if usuario:
                session['user_id'] = str(usuario.id) 
                session['rol'] = 'user'
                session['numero_acceso'] = codigo
                return redirect(url_for('panel_usuario'))
            else:
                return render_template('login.html', error="Nombre de usuario y/o código de acceso inválido.")
        
        return render_template('login.html', error="Código de acceso inválido.")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/panel')
@login_required
def panel_inicio():
# ... (Ruta sin cambios) ...
    if g.rol == 'admin':
        return redirect(url_for('panel_admin'))
    elif g.rol == 'user':
        # Redirige a la vista de "Crear Nuevo Reporte" (ruta por defecto del usuario)
        return redirect(url_for('panel_usuario')) 
    else:
        return redirect(url_for('logout'))

# --- Rutas de Usuario (Sin cambios) ---

@app.route('/mis_tickets')
@login_required
def panel_usuario():
# ... (Ruta sin cambios) ...
    """Ruta principal del usuario: solo muestra el formulario de nuevo reporte."""
    if g.rol != 'user':
        return redirect(url_for('panel_admin')) 

    zonas = Zona.query.order_by(Zona.nombre).all()
    
    # mostrando_lista=False indica que se debe renderizar el formulario
    return render_template('panel_usuario.html', zonas=zonas, mostrando_lista=False)


@app.route('/tickets/gestion')
@login_required
def lista_tickets_usuario():
# ... (Ruta sin cambios) ...
    """Nueva ruta para la pestaña de gestión y listado de tickets."""
    if g.rol != 'user':
        return redirect(url_for('panel_admin')) 

    try:
        user_db_id = int(g.user_id)
    except ValueError:
        abort(403) 
    
    # Filtro estricto por el ID del usuario logueado
    query = Ticket.query.filter_by(creador_id=user_db_id).order_by(Ticket.fecha_creacion.desc())
    
    search_ref = request.args.get('search_ref', '').strip()
    
    if search_ref:
        query = query.filter(Ticket.reference_number.like(f'%{search_ref}%'))
        
    # Usar join con isouter=True para manejar tickets sin zona
    tickets = query.join(Zona, Ticket.zona_id == Zona.id, isouter=True).all()
    
    # mostrando_lista=True indica que se debe renderizar la lista
    return render_template('panel_usuario.html', 
                           tickets=tickets, 
                           search_ref=search_ref, 
                           mostrando_lista=True)

@app.route('/ticket/crear', methods=['POST'])
@login_required
def crear_ticket():
# ... (Ruta sin cambios) ...
    if g.rol != 'user':
         return "Solo los usuarios (4 dígitos) pueden crear tickets.", 403

    titulo = request.form.get('titulo', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    zona_id = request.form.get('zona_id') 
    
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
            import time
            unique_filename = f"{int(time.time())}_{filename}" 
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            photo_path = unique_filename 

    zona_to_save = int(zona_id) if zona_id and zona_id.isdigit() and int(zona_id) != 0 else None
    
    nuevo_ticket = Ticket(
        titulo=titulo, 
        descripcion=descripcion, 
        creador_id=creador_id_int, 
        estado='Abierto', 
        photo_path=photo_path, 
        zona_id=zona_to_save
    )
    db.session.add(nuevo_ticket)
    db.session.commit()
    nuevo_ticket.reference_number = str(nuevo_ticket.id).zfill(4)
    db.session.commit()
    
    # Después de crear, redirige a la gestión de tickets
    return redirect(url_for('lista_tickets_usuario')) 

# --- Rutas de Administrador (Sin cambios estructurales en panel) ---

@app.route('/admin', methods=['GET'])
@admin_required
def panel_admin():
# ... (Ruta sin cambios) ...
    """Ruta principal del admin: Muestra la gestión de tickets."""
    search_ref = request.args.get('search_ref', '').strip()
    
    query = Ticket.query.join(Usuario, Ticket.creador_id == Usuario.id, isouter=True)\
                        .join(Zona, Ticket.zona_id == Zona.id, isouter=True)\
                        .order_by(Ticket.fecha_creacion.desc())

    if search_ref:
        search_term = f"%{search_ref}%"
        query = query.filter(
            db.or_(
                Ticket.reference_number.ilike(search_term), 
                Ticket.titulo.ilike(search_term)
            )
        )
        
    all_tickets = query.all()

    status_groups = defaultdict(list)
    status_counts = {'Abierto': 0, 'En Progreso': 0, 'Resuelto': 0, 'Rechazado': 0}
    
    for ticket in all_tickets:
        estado = ticket.estado or 'Abierto'
        
        if estado in status_counts:
            status_groups[estado].append(ticket)
            status_counts[estado] += 1
            
    # Solo pasamos datos de tickets y la pestaña activa
    return render_template('panel_admin.html', 
                           status_counts=status_counts, 
                           status_groups=status_groups,
                           search_ref=search_ref,
                           tickets=all_tickets, 
                           active_tab='tickets') # Pestaña activa por defecto


@app.route('/admin/usuarios', methods=['GET'])
@admin_required
def gestion_usuarios_admin():
# ... (Ruta sin cambios) ...
    """Nueva ruta para la pestaña de gestión de usuarios."""
    usuarios = Usuario.query.filter_by(rol='user').order_by(Usuario.numero_acceso).all() 
    return render_template('panel_admin.html', 
                           usuarios=usuarios,
                           active_tab='usuarios') # Pestaña activa 'usuarios'


@app.route('/admin/usuario/crear', methods=['POST'])
@admin_required
def crear_usuario():
# ... (Ruta sin cambios) ...
    nombre_completo = request.form.get('nombre_completo', '').strip()
    numero_acceso = request.form.get('numero_acceso', '').strip()
    
    if len(numero_acceso) != 4 or not numero_acceso.isdigit():
        return "El código de acceso debe ser de 4 dígitos.", 400

    if Usuario.query.filter_by(numero_acceso=numero_acceso).first():
        return "Ya existe un usuario con ese código de acceso.", 400
        
    nuevo_usuario = Usuario(nombre_completo=nombre_completo, numero_acceso=numero_acceso, rol='user')
    db.session.add(nuevo_usuario)
    db.session.commit()
    # Redirigir a la nueva pestaña de Usuarios
    return redirect(url_for('gestion_usuarios_admin'))


@app.route('/admin/usuario/eliminar', methods=['POST'])
@admin_required
def eliminar_usuario():
# ... (Ruta sin cambios) ...
    """Elimina un usuario y todos sus tickets y comentarios asociados."""
    user_id_a_eliminar = request.form.get('eliminar_usuario_id')
    
    if user_id_a_eliminar and user_id_a_eliminar.isdigit():
        user_id_int = int(user_id_a_eliminar)
        usuario = Usuario.query.get(user_id_int)
        
        if usuario:
            # 1. Prevenir la eliminación de la cuenta de administrador por seguridad
            if usuario.rol == 'admin':
                # Mensaje simple de depuración, redirigir sin eliminar
                print("Intento de eliminar administrador bloqueado.") 
                return redirect(url_for('gestion_usuarios_admin'))
            
            # 2. ELIMINAR DATOS ASOCIADOS PARA PRESERVAR LA INTEGRIDAD REFERENCIAL
            # Se requiere eliminar manualmente los Comentarios y Tickets creados por el usuario.

            # Eliminar todos los Comentarios asociados a los Tickets creados por este usuario
            tickets_del_usuario = Ticket.query.filter_by(creador_id=user_id_int).all()
            for ticket in tickets_del_usuario:
                 # El delete con synchronize_session=False es más eficiente para eliminaciones masivas
                 Comentario.query.filter_by(ticket_id=ticket.id).delete(synchronize_session=False)

            # Eliminar todos los Comentarios hechos *por* el usuario (en cualquier ticket)
            Comentario.query.filter_by(usuario_id=str(user_id_int)).delete(synchronize_session=False)

            # 3. ELIMINAR TICKETS CREADOS POR EL USUARIO
            Ticket.query.filter_by(creador_id=user_id_int).delete(synchronize_session=False)
            
            # 4. ELIMINAR USUARIO
            db.session.delete(usuario)
            db.session.commit()
            
    # Redirigir a la pestaña de Usuarios
    return redirect(url_for('gestion_usuarios_admin'))


@app.route('/admin/zonas/view', methods=['GET'])
@admin_required
def gestion_zonas_admin():
# ... (Ruta sin cambios) ...
    """Nueva ruta para la pestaña de gestión de zonas."""
    zonas = Zona.query.order_by(Zona.nombre).all()
    return render_template('panel_admin.html', 
                           zonas=zonas,
                           active_tab='zonas') # Pestaña activa 'zonas'


@app.route('/admin/zonas', methods=['POST'])
@admin_required
def gestionar_zonas():
# ... (Ruta sin cambios) ...
    nombre_zona = request.form.get('nombre_zona', '').strip()
    if nombre_zona:
        if not Zona.query.filter_by(nombre=nombre_zona).first():
            nueva_zona = Zona(nombre=nombre_zona)
            db.session.add(nueva_zona)
            db.session.commit()
        # Redirigir a la nueva pestaña de Zonas
        return redirect(url_for('gestion_zonas_admin'))

    zona_id_a_eliminar = request.form.get('eliminar_zona_id')
    if zona_id_a_eliminar and zona_id_a_eliminar.isdigit():
        zona = Zona.query.get(int(zona_id_a_eliminar))
        if zona:
            Ticket.query.filter_by(zona_id=zona.id).update({'zona_id': None}, synchronize_session=False)
            db.session.delete(zona)
            db.session.commit()
        # Redirigir a la nueva pestaña de Zonas
        return redirect(url_for('gestion_zonas_admin'))
        
    return redirect(url_for('gestion_zonas_admin'))

# --- Rutas de Tickets (Compartidas) ---

@app.route('/ticket/<int:ticket_id>')
@login_required
def ver_ticket(ticket_id):
# ... (Ruta sin cambios estructurales) ...
    ticket = Ticket.query.get_or_404(ticket_id)
    
    puede_ver = False
    if g.rol == 'admin':
        puede_ver = True
    elif g.rol == 'user' and str(ticket.creador_id) == g.user_id:
        puede_ver = True
        
        # Lógica para marcar notificaciones como leídas cuando el usuario ve el ticket
        Notificacion.query.filter_by(
            usuario_id=int(g.user_id), 
            ticket_id=ticket.id,
            leida=False
        ).update({'leida': True}, synchronize_session=False)
        db.session.commit()
        # g.notificaciones_sin_leer_count se actualizará en el siguiente request.
    
    if not puede_ver:
        abort(403)

    creador = Usuario.query.get(ticket.creador_id)
    creador_nombre = creador.nombre_completo if creador else 'N/A'
    creador_acceso = creador.numero_acceso if creador else 'N/A'

    comentarios = Comentario.query.filter_by(ticket_id=ticket_id).order_by(Comentario.fecha_creacion).all()
    
    user_ids = [c.usuario_id for c in comentarios if c.usuario_id.isdigit()]
    
    users_who_commented = Usuario.query.filter(Usuario.id.in_(user_ids)).all()
    user_map = {str(u.id): u.nombre_completo for u in users_who_commented}
    user_map['ADMIN_ID'] = 'ADMINISTRADOR' 

    for c in comentarios:
        c.nombre_completo = user_map.get(c.usuario_id, f"USR {c.usuario_acceso}") 
    
    puede_comentar = (g.rol == 'admin') or (g.rol == 'user' and str(ticket.creador_id) == g.user_id)

    zonas = Zona.query.order_by(Zona.nombre).all()
    
    return render_template('ver_ticket.html', 
        ticket=ticket, 
        comentarios=comentarios, 
        creador_nombre=creador_nombre,
        creador_acceso=creador_acceso,
        puede_comentar=puede_comentar,
        zonas=zonas 
    )

@app.route('/ticket/<int:ticket_id>/comentar', methods=['POST'])
@login_required
def comentar_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    texto = request.form.get('texto', '').strip()
    
    if not texto:
        flash('El comentario no puede estar vacío.', 'warning')
        return redirect(url_for('ver_ticket', ticket_id=ticket_id))

    if g.rol == 'user' and str(ticket.creador_id) != g.user_id: 
        abort(403) 

    nuevo_comentario = Comentario(
        texto=texto,
        ticket_id=ticket_id,
        usuario_id=g.user_id, 
        usuario_acceso=g.numero_acceso
    )
    db.session.add(nuevo_comentario)
    
    # --- Lógica de Notificación por Comentario de Admin ---
    if g.rol == 'admin':
        try:
            creador_id_int = int(ticket.creador_id)
            crear_notificacion(
                usuario_id=creador_id_int,
                ticket_id=ticket.id,
                tipo='comentario',
                mensaje=f"El administrador ha añadido un comentario en su ticket #{ticket.reference_number}."
            )
        except ValueError:
            print("Error: El ID del creador no es un entero.")
    # ----------------------------------------------------
    
    db.session.commit()
    flash('Comentario añadido correctamente.', 'success')
    return redirect(url_for('ver_ticket', ticket_id=ticket_id))

@app.route('/ticket/<int:ticket_id>/estado', methods=['POST'])
@admin_required
def cambiar_estado(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    nuevo_estado = request.form.get('estado')
    motivo_rechazo = request.form.get('motivo_rechazo', '').strip()
    
    estados_validos = ['Abierto', 'En Progreso', 'Resuelto', 'Rechazado']
    if nuevo_estado not in estados_validos:
        flash('Estado inválido.', 'danger')
        return redirect(url_for('ver_ticket', ticket_id=ticket_id))

    estado_anterior = ticket.estado
    
    ticket.estado = nuevo_estado
    
    if nuevo_estado == 'Rechazado' and motivo_rechazo:
        ticket.motivo_rechazo = motivo_rechazo
    elif nuevo_estado != 'Rechazado':
        ticket.motivo_rechazo = None

    # --- Lógica de Notificación por Cambio de Estado ---
    if nuevo_estado != estado_anterior:
        try:
            creador_id_int = int(ticket.creador_id)
            crear_notificacion(
                usuario_id=creador_id_int, 
                ticket_id=ticket.id, 
                tipo='estado_cambiado', 
                mensaje=f"El estado de su ticket #{ticket.reference_number} ha cambiado a: {nuevo_estado.upper()}"
            )
        except ValueError:
            print("Error: El ID del creador no es un entero.")
    # --------------------------------------------------

    db.session.commit()
    flash(f"Estado actualizado a {nuevo_estado.upper()}.", 'success')
    return redirect(url_for('ver_ticket', ticket_id=ticket_id))

@app.route('/ticket/<int:ticket_id>/editar/admin', methods=['POST'])
@admin_required
def editar_ticket_admin(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    
    titulo_anterior = ticket.titulo
    descripcion_anterior = ticket.descripcion
    zona_id_anterior = ticket.zona_id
    reference_number_anterior = ticket.reference_number

    ticket.titulo = request.form.get('titulo', ticket.titulo)
    ticket.descripcion = request.form.get('descripcion', ticket.descripcion)
    reference_number = request.form.get('reference_number', '').strip()
    
    zona_id = request.form.get('zona_id')
    zona_to_save = int(zona_id) if zona_id and zona_id.isdigit() and int(zona_id) != 0 else None
    ticket.zona_id = zona_to_save
    
    if reference_number and len(reference_number) == 4:
         ticket.reference_number = reference_number

    # --- Lógica de Notificación por Modificación de Datos ---
    ha_habido_cambio = (
        ticket.titulo != titulo_anterior or
        ticket.descripcion != descripcion_anterior or
        ticket.zona_id != zona_id_anterior or
        ticket.reference_number != reference_number_anterior
    )
    
    if ha_habido_cambio:
        try:
            creador_id_int = int(ticket.creador_id)
            crear_notificacion(
                usuario_id=creador_id_int, 
                ticket_id=ticket.id, 
                tipo='modificacion', 
                mensaje=f"El administrador ha actualizado la información básica de su ticket #{ticket.reference_number}."
            )
        except ValueError:
            print("Error: El ID del creador no es un entero.")
    # --------------------------------------------------------

    db.session.commit()
    flash('Datos del ticket actualizados por el administrador.', 'success')
    return redirect(url_for('ver_ticket', ticket_id=ticket_id))

@app.route('/ticket/<int:ticket_id>/acusar_cierre', methods=['POST'])
@login_required
def acusar_cierre(ticket_id):
# ... (Ruta sin cambios) ...
    ticket = Ticket.query.get_or_404(ticket_id)
    
    if g.rol != 'user' or str(ticket.creador_id) != g.user_id:
        abort(403)
    
    if ticket.estado in ['Resuelto', 'Rechazado'] and not ticket.acusado_por_usuario:
        ticket.acusado_por_usuario = True
        db.session.commit()
        flash('Ticket archivado correctamente.', 'success')
        
    return redirect(url_for('ver_ticket', ticket_id=ticket_id))


# --- Rutas de Archivos (Sin cambios) ---

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Inicialización (Modificado) ---

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        
    with app.app_context():
        # Se recreará la base de datos o se añadirán las tablas faltantes si no existe
        db.create_all() 
        
        admin = Usuario.query.filter_by(numero_acceso='9898').first()
        if not admin:
            admin_user = Usuario(
                nombre_completo='ADMINISTRADOR',
                numero_acceso='9898',
                rol='admin'
            )
            db.session.add(admin_user)
            db.session.commit()
            
    app.run(debug=True)
