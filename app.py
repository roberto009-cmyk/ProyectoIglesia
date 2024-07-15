
import io
import os
from pydoc import text
from flask import Flask, jsonify, render_template, request, redirect, send_file, url_for, flash, session
from mysqlx import Session
from openpyxl import Workbook
import pandas as pd
import pyodbc
import calendar
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from requests import Response
import xlsxwriter
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.secret_key = 'your_secret_key'

#################  Configuración de la conexión a la base de datos  ###################
SERVER = 'DESKTOP-INC59M1\\SQLEXPRESS'
DATABASE = 'MiembrosDB'
USERNAME = 'sa'
PASSWORD = '123'

def establecer_conexion():
    conn_str = f'DRIVER={{SQL Server}};SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD}'
    return pyodbc.connect(conn_str)

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

################# METODO INICAR SESION LOGIN  #####################

@login_manager.user_loader
def load_user(user_id):
    conn = establecer_conexion()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Usuarios WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return User(id=user[0], username=user[1], password=user[2])
    return None



##########         METODO LOGIN           #################

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = establecer_conexion()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM Usuarios WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        if user and bcrypt.check_password_hash(user[2], password):
            login_user(User(id=user[0], username=user[1], password=user[2]))
            session['logged_in'] = True  # Marcar sesión como iniciada en la sesión de Flask
            return redirect(url_for('index'))
        else:
            flash('Nombre de usuario o contraseña incorrectos', 'error')
    return render_template('login.html')

################ METODO SALIR Y LIMPIAR SESION ########################

@app.route('/logout')
@login_required
def logout():
    session.clear()  # Limpiar toda la sesión de Flask
    logout_user()
    return redirect(url_for('login'))



########### METODO REINICIAR ID SI SE ELIMINAN TODOS LOS DATOS DE LA TABLA MIEMBROS  #########################

@app.route('/reiniciar_id_miembros', methods=['POST'])
@login_required
def reiniciar_id_miembros():
    try:
        # Eliminar todos los registros de la tabla
        conn = establecer_conexion()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM Miembros')
        conn.commit()

        # Reiniciar el contador de identidad
        cursor.execute('DBCC CHECKIDENT (Miembros, RESEED, 0)')
        conn.commit()

        flash('El contador de identidad de Miembros ha sido reiniciado.', 'success')
    except Exception as e:
        flash(f'Error al reiniciar el contador de identidad: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('index'))


###########  METODO FUNCION PAGINA Y AGREGADO EL METODO FILTRO BUSCAR MIEMBRO Y MOSTRAR Cantidades  #####################

@app.route('/')
@login_required
def index():
    conn = establecer_conexion()
    cursor = conn.cursor()

    # Obtener el término de búsqueda desde la URL
    query = request.args.get('query', '')

    # Obtener el parámetro mostrar desde la URL y ajustar la consulta SQL
    mostrar = request.args.get('mostrar', '10')  # Por defecto mostrar 10 elementos por página

    # Consulta SQL base para obtener los miembros activos
    sql_query = 'SELECT * FROM Miembros WHERE activo = 1'
    params = []

    if query:
        sql_query += ' AND nombre LIKE ?'
        query_param = f"%{query}%"
        params.append(query_param)

    if mostrar.isdigit() and int(mostrar) > 0:
        sql_query = f'SELECT TOP {int(mostrar)} * FROM ({sql_query}) AS T'

    cursor.execute(sql_query, params)
    miembros = cursor.fetchall()
    conn.close()
    return render_template('index.html', miembros=miembros, query=query, mostrar=mostrar)



###########################   METODO AGREGAR MIEMBRO     ########################################

@app.route('/AgregarMiembro', methods=['GET', 'POST'])
@login_required
def add_member():
    if request.method == 'POST':
        nombre = request.form['nombre']
        colonia = request.form['colonia']
        telefono = request.form['telefono']

        conn = establecer_conexion()
        cursor = conn.cursor()

        # Verificar si el miembro ya existe
        cursor.execute('SELECT * FROM Miembros WHERE nombre = ? AND colonia = ? AND telefono = ?', (nombre, colonia, telefono))
        existing_member = cursor.fetchone()

        if existing_member:
            flash('Este miembro ya existe en la base de datos.', 'warning')
        else:
            # Insertar el nuevo miembro
            cursor.execute('INSERT INTO Miembros (nombre, colonia, telefono) VALUES (?, ?, ?)',
                           (nombre, colonia, telefono))
            conn.commit()
            conn.close()
            flash('Miembro agregado correctamente.', 'success')
            return redirect(url_for('index'))

    return render_template('AgregarMiembro.html')


########## metodo boton confirmar eliminar miembro ##############

@app.route('/confirmar_eliminarmiembro/<int:id>', methods=['GET', 'POST'])
@login_required
def confirmar_eliminarmiembro(id):
    conn = establecer_conexion()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Miembros WHERE id = ?', (id,))
    miembro = cursor.fetchone()
    conn.close()

    if request.method == 'POST':
        # Eliminar el miembro de la base de datos
        conn = establecer_conexion()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM Miembros WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        flash(f'Miembro {miembro.nombre} ha sido eliminado correctamente.', 'success')
        return redirect(url_for('index'))

    return render_template('confirmar_eliminarmiembro.html', miembro=miembro)

################## METODO BOTON EDITAR MIEMBRO ######################

@app.route('/editar_miembro/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_miembro(id):
    conn = establecer_conexion()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Miembros WHERE id = ?', (id,))
    miembro = cursor.fetchone()  # Obtener el miembro como una tupla

    if request.method == 'POST':
        nombre = request.form['nombre']
        colonia = request.form['colonia']
        telefono = request.form['telefono']

        cursor.execute('UPDATE Miembros SET nombre = ?, colonia = ?, telefono = ? WHERE id = ?',
                       (nombre, colonia, telefono, id))
        conn.commit()
        conn.close()
        flash(f'Miembro {miembro[1]} ha sido actualizado correctamente.', 'success')
        return redirect(url_for('index'))

    conn.close()

    # Pasar los datos del miembro al formulario de edición
    miembro_dict = {
        'id': miembro[0],
        'nombre': miembro[1],
        'colonia': miembro[2],
        'telefono': miembro[3]
    }

    return render_template('editar_miembro.html', miembro=miembro_dict)



############ metodo BUSCAR miembros ################

@app.route('/search', methods=['GET'])
@login_required
def search():
    query = request.args.get('query', '')  # Obtener el término de búsqueda desde la URL
    conn = establecer_conexion()
    cursor = conn.cursor(dictionary=True)
    
    if query:
        cursor.execute('SELECT * FROM Miembros WHERE nombre LIKE ?', ('%' + query + '%',))
    else:
        cursor.execute('SELECT * FROM Miembros WHERE activo = 1')  # Búsqueda estándar sin filtro
    
    miembros = cursor.fetchall()
    conn.close()
    
    if request.is_xhr:  # Si es una solicitud AJAX, devolver solo los resultados de la búsqueda o un mensaje si no hay resultados
        if miembros:
            return render_template('miembros-table', miembros=miembros)
        else:
            return ''
    else:  # Si es una solicitud normal, devolver toda la página HTML
        return render_template('index.html', miembros=miembros)


############################# METODO PARA GUARDAR LOS DATOS DE TABLA RESUMEN EN LA BASE DE DATOS ##################
# conn = establecer_conexion()
        #   cursor = conn.cursor() ###################

# Ruta para guardar las asistencias en la base de datos
@app.route('/guardar_asistencias', methods=['POST'])
def guardar_asistencias():
    data = request.get_json()
    conn = establecer_conexion()
    cursor = conn.cursor()

    try:
        for memberId, memberData in data.items():
            for key, value in memberData.items():
                year, month, day = map(int, key.split('-'))
                fecha = f"{year}-{month}-{day}"
                asistencia = 1 if value == '*' else 0  # Convertir '*' a 1, 'F' a 0

                # Guardar solo si es '*' o 'F'
                if value == '*' or value == 'F':
                    query = "INSERT INTO PersonaAsistencia (miembro_id, fecha, Asistencia) VALUES (?, ?, ?)"
                    cursor.execute(query, (memberId, fecha, asistencia))
        
        conn.commit()
        return jsonify({'message': 'Datos guardados correctamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)})
    
    finally:
        cursor.close()
        conn.close()

#################################


############## //////////////////////METODO PARA ASISTENCIAS ////////////////////////////// 

@app.route('/asistencias', methods=['GET', 'POST'])
@login_required
def asistencias():
    import datetime
    # Obtener el mes y año actual
    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.month
    
    # Obtener la lista de miembros activos
    conn = establecer_conexion()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nombre FROM Miembros WHERE activo = 1')
    miembros = cursor.fetchall()
    conn.close()

    # Si se envía el formulario, obtener el mes y año seleccionado
    if request.method == 'POST':
        selected_month = int(request.form.get('mes'))
        selected_year = int(request.form.get('anio'))
    else:
        selected_month = current_month
        selected_year = current_year

    # Obtener el nombre del mes seleccionado
    month_name = calendar.month_name[selected_month]

    # Obtener el número de días del mes seleccionado
    num_days = calendar.monthrange(selected_year, selected_month)[1]

    # Crear una lista de días del mes
    days = [datetime.datetime(selected_year, selected_month, day) for day in range(1, num_days + 1)]

    # Calcular el día de la semana en que comienza el mes (0: lunes, 6: domingo)
    first_day_of_month = datetime.datetime(selected_year, selected_month, 1)
    inicioSemana = first_day_of_month.weekday()

    # Lista de nombres de días de la semana en español
    dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

    # Obtener asistencias guardadas para el mes y año seleccionado (simulado)
    # Aquí deberías tener la lógica para obtener las asistencias de la base de datos
    # Vamos a simular con datos de ejemplo
    asistencias = {}

    for miembro in miembros:
        # Simulación de datos de asistencia vacíos inicialmente
        asistencias[miembro[0]] = {
            'nombre': miembro[1],
            'asistencias': [''] * num_days  # Inicialmente todas las asistencias están vacías
        }

    # Rango de años para la selección
    year_range = range(current_year - 5, current_year + 1)

    # Renderizar la plantilla con los datos y el módulo calendar
    return render_template('Asistencias.html', 
                           miembros=miembros, 
                           month_name=month_name, 
                           selected_month=selected_month,
                           selected_year=selected_year,
                           days=days,
                           asistencias=asistencias,
                           current_year=current_year,
                           calendar=calendar,
                           num_days=num_days,
                           years=year_range,
                           inicioSemana=inicioSemana,
                           dias_semana=dias_semana)  # Pasar dias_semana al contexto





############## Intento de deshabilitar retroceso #################
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

############### METODO PARA Insertar el usuario inicial en la base de datos si no existe  ##################
def insertar_usuario_inicial():
    conn = establecer_conexion()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Usuarios WHERE username = ?', ('iglesia.admin@gmail.com',))
    user = cursor.fetchone()
    if not user:
        password_hash = bcrypt.generate_password_hash('admin').decode('utf-8')
        cursor.execute('INSERT INTO Usuarios (username, password) VALUES (?, ?)', ('iglesia.admin@gmail.com', password_hash))
        conn.commit()
    conn.close()


############### METODO EXPORTAR EXCEL MIEMBROS ##############################

@app.route('/export_excel')
@login_required
def export_excel():
    conn = establecer_conexion()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nombre, colonia, telefono FROM Miembros WHERE activo = 1')
    miembros = cursor.fetchall()
    conn.close()
    from datetime import datetime

    # Construir una lista de diccionarios con los datos
    data = [{'ID': miembro[0], 'Nombre': miembro[1], 'Colonia': miembro[2], 'Teléfono': miembro[3]} for miembro in miembros]

    # Convertir los datos en un DataFrame de pandas
    df = pd.DataFrame(data)

    # Obtener el nombre del mes actual y el año
    mes_actual = datetime.now().strftime('%B %Y')

    # Guardar el DataFrame como archivo Excel con el título en la hoja
    filename = f'miembros_{datetime.now().strftime("%B_%Y")}.xlsx'
    df.to_excel(filename, index=False, sheet_name=mes_actual)

    # Enviar el archivo Excel como respuesta para descarga
    return send_file(filename, as_attachment=True)

################### METODO EXPORTAR A PDF ######################################
@app.route('/export_pdf')
@login_required
def export_pdf():
    # Conexión a la base de datos y consulta
    conn = establecer_conexion()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nombre, colonia, telefono FROM Miembros WHERE activo = 1')
    miembros = cursor.fetchall()
    conn.close()
    from datetime import datetime

    # Verificar los datos obtenidos
    print(miembros)  # Imprimir para verificar la estructura de los datos

    # Obtener el mes y año actual
    now = datetime.now()
    month_year = now.strftime('%B %Y')
    filename = f'miembros_{month_year}.pdf'

    # Crear el PDF
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter

    # Encabezado con ícono de la iglesia a la derecha
    c.setFont('Helvetica-Bold', 16)
    c.drawString(inch, height - inch, f"Miembros, {month_year}")
    
    # Insertar el ícono de la iglesia
    church_icon_path = 'static/IglesiaPDFIcono.png'  # Ruta al archivo del ícono de la iglesia
    c.drawInlineImage(church_icon_path, width - inch - 50, height - inch - 10, width=50, height=50)

    # Encabezado
    c.setFont('Helvetica-Bold', 16)
    c.drawString(inch, height - inch, f"Miembros, {month_year}")

    # Línea divisoria al comienzo
    c.line(inch, height - inch - 10, width - inch, height - inch - 10)

    # Preparar datos para la tabla
    data = [['ID', 'Nombre', 'Colonia', 'Teléfono']]  # Encabezados de columnas
    data.extend([[miembro[0], miembro[1], miembro[2], miembro[3]] for miembro in miembros])

    # Crear y configurar la tabla
    table = Table(data, colWidths=[1.5 * inch] * 4)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ])
    table.setStyle(style)

    # Calcular la posición centrada de la tabla verticalmente
    table.wrapOn(c, width, height)
    table_width, table_height = table.wrap(0, 0)
    x_position = (width - table_width) / 2
    y_position = (height - table_height) / 1.30  # Centra verticalmente

    # Generar la tabla y añadirla al PDF
    table.drawOn(c, x_position, y_position)

    # Línea divisoria al final (a 1 pulgada desde el borde inferior)
    bottom_line_y = inch  # Ajusta esta posición según sea necesario
    c.line(inch, bottom_line_y, width - inch, bottom_line_y)

    # Pie de página con número de página
    c.setFont('Helvetica', 10)
    c.drawString(inch, inch / 2, "Página 1")

    # Guardar el PDF
    c.save()

    # Enviar el archivo PDF como respuesta para descarga
    return send_file(filename, as_attachment=True)

###################################

if __name__ == '__main__':
    insertar_usuario_inicial()
    app.run(debug=True, port=8080)
