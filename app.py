from flask import Flask, render_template, request, redirect, session
from pymongo import MongoClient
from geopy.geocoders import Nominatim
from bson import ObjectId
import re
import datetime

app = Flask(__name__)
app.secret_key = 'mysecretkey'

# Conexión al servidor de MongoDB
client = MongoClient('mongodb://localhost:27017')
db = client['ExploreCheck2']  # Reemplaza 'nombre_base_de_datos' con el nombre de tu base de datos
usuarios_collection = db['usuario']  # Reemplaza 'usuario' con el nombre de tu colección de usuarios
amigos_collection = db['amigos']  # Reemplaza 'amigos' con el nombre de tu colección de amigos
lugares_collection = db['lugar']
checks_collection = db['check']

def calcular_promedios():
    lugares = lugares_collection.find()
    promedios = {}

    for lugar in lugares:
        lugar_nombre = lugar['nombre']
        calificaciones_lugar = checks_collection.find({'lugar': lugar_nombre, 'tipo': 'lugar'})
        total_calificaciones = 0
        num_calificaciones = 0

        for calificacion in calificaciones_lugar:
            total_calificaciones += calificacion['puntuacion']
            num_calificaciones += 1

        promedio = total_calificaciones / num_calificaciones if num_calificaciones > 0 else 0
        promedios[lugar_nombre] = promedio

    return promedios

@app.route('/')
def index():
    lugares = lugares_collection.find()
    promedios = calcular_promedios()

    lugares_con_promedio = [(lugar['nombre'], promedios.get(lugar['nombre'], 0)) for lugar in lugares]

    return render_template('index.html', lugares_con_promedio=lugares_con_promedio)

@app.route('/buscar_lugar', methods=['GET', 'POST'])
def buscar_lugar():
    if request.method == 'POST':
        search_term = request.form.get('nombre_lugar', '').lower()

        # Obtener todos los lugares
        lugares = lugares_collection.find()

        # Obtener los promedios nuevamente
        promedios = calcular_promedios()

        # Crear una lista con las coincidencias de búsqueda
        lugares_coincidencias = []
        for lugar in lugares:
            lugar_nombre = lugar['nombre']
            if search_term.lower() in lugar_nombre.lower():
                promedio = promedios.get(lugar_nombre, 0)
                lugares_coincidencias.append((lugar_nombre, promedio))

        return render_template('index.html', lugares_con_promedio=lugares_coincidencias)
    else:
        # Si es un GET, redirige a la página principal
        return redirect('/')

@app.route('/info/<nombre_lugar>')
def lugar_info(nombre_lugar):
    lugar = lugares_collection.find_one({'nombre': nombre_lugar})

    if lugar is None:
        # Manejar el caso donde el lugar no existe
        return "El lugar no existe."

    # Obtener los últimos 5 comentarios del lugar
    comentarios_lugar = checks_collection.find({'lugar': nombre_lugar, 'tipo': 'lugar'}).sort('_id', -1).limit(5)

    # Obtener los puntos de interés del lugar
    puntos_interes = lugar.get('puntos_interes', [])

    # Crear una lista para almacenar los comentarios de cada punto de interés
    comentarios_puntos_interes = {}

    for punto in puntos_interes:
        comentarios_punto = checks_collection.find({'lugar': nombre_lugar, 'punto': punto['nombre'], 'tipo': 'punto_interes'}).sort('_id', -1).limit(5)
        comentarios_puntos_interes[punto['nombre']] = comentarios_punto

    # Calcular promedios de los puntos de interés
    promedios_puntos_interes = calcular_promedios_puntos_interes(nombre_lugar)

    return render_template('info.html', lugar=lugar, comentarios_lugar=comentarios_lugar, comentarios_puntos_interes=comentarios_puntos_interes, promedios_puntos_interes=promedios_puntos_interes)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Obtener los datos del formulario
        username = request.form['username']
        password = request.form['password']

        # Verificar los datos en la colección 'usuario' de MongoDB
        user = usuarios_collection.find_one({'username': username, 'password': password})

        if user:
            # Inicio de sesión exitoso
            session['username'] = user['username']
            session['nombre'] = user['nombre']
            session['apellido'] = user['apellido']
            return redirect('/dashboard')
        else:
            # Inicio de sesión fallido
            return render_template('login.html')
    else:
        return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Obtener los datos del formulario
        username = request.form['username']
        password = request.form['password']
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        correo = request.form['correo']

        # Guardar los datos en la colección 'usuario' de MongoDB
        user = {
            'username': username,
            'password': password,
            'nombre': nombre,
            'apellido': apellido,
            'correo': correo
        }
        usuarios_collection.insert_one(user)

        # Establecer la sesión del usuario
        session['username'] = username
        session['nombre'] = nombre
        session['apellido'] = apellido

        # Redirigir al dashboard
        return redirect('/dashboard')
    else:
        return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    if 'username' in session:
        # Obtener amigos del usuario
        amigos = amigos_collection.find({'usuario': session['username']})
        amigos_list = [amigo['amigo'] for amigo in amigos]

        # Obtener los últimos 10 checks del usuario
        mis_ultimos_checks = checks_collection.find({'usuario': session['username']}).sort('_id', -1).limit(10)

        # Obtener los últimos 10 checks de los amigos
        amigos_ultimos_checks = checks_collection.find({'usuario': {'$in': amigos_list}}).sort('_id', -1).limit(10)

        return render_template('dashboard.html', username=session['username'], nombre=session['nombre'], apellido=session['apellido'], amigos=amigos_list, mis_ultimos_checks=mis_ultimos_checks, amigos_ultimos_checks=amigos_ultimos_checks)
    else:
        return redirect('/login')



@app.route('/add_friend', methods=['GET', 'POST'])
def add_friend():
    if 'username' in session:
        if request.method == 'POST':
            amigo = request.form['amigo']

            # Verificar si el amigo ya está agregado
            existing_amigo = amigos_collection.find_one({'usuario': session['username'], 'amigo': amigo})
            if existing_amigo:
                return redirect('/dashboard')

            # Agregar el amigo al usuario actual
            amigo_data = {
                'usuario': session['username'],
                'amigo': amigo
            }
            amigos_collection.insert_one(amigo_data)

            # Agregar al usuario actual como amigo del amigo
            amigo_data_inverse = {
                'usuario': amigo,
                'amigo': session['username']
            }
            amigos_collection.insert_one(amigo_data_inverse)

            return redirect('/dashboard')
        else:
            usuarios = usuarios_collection.find({'username': {'$ne': session['username']}})
            return render_template('agregar_amigo.html', usuarios=usuarios)
    else:
        return redirect('/login')



@app.route('/search_user', methods=['POST'])
def search_user():
    if 'username' in session:
        search_term = request.form['search_term']
        search_regex = f'.*{search_term}.*'
        amigos = amigos_collection.find({'usuario': session['username']})
        amigos_list = [amigo['amigo'] for amigo in amigos]
        usuarios = usuarios_collection.find({
            '$or': [
                {'username': {'$regex': search_regex, '$options': 'i'}},
                {'nombre': {'$regex': search_regex, '$options': 'i'}},
                {'apellido': {'$regex': search_regex, '$options': 'i'}}
            ],
            'username': {'$ne': session['username']}
        })
        return render_template('buscar_amigo.html', usuarios=usuarios, amigos_list=amigos_list)
    else:
        return redirect('/login')

@app.route('/search_place', methods=['POST'])
def search_place():
    if 'username' in session:
        search_term = request.form['place']
        geolocator = Nominatim(user_agent="my_app")
        location = geolocator.geocode(search_term)

        if location is not None:
            latitud = location.latitude
            longitud = location.longitude
            lugar_data = {
                'nombre': search_term,
                'latitud': latitud,
                'longitud': longitud
            }
            lugares_collection.insert_one(lugar_data)

        return render_template('search_place.html', username=session['username'], nombre=session['nombre'], apellido=session['apellido'])
    else:
        return redirect('/login')

@app.route('/remove_friend', methods=['POST'])
def remove_friend():
    if 'username' in session:
        amigo = request.form['amigo']
        amigos_collection.delete_one({'usuario': session['username'], 'amigo': amigo})
        amigos_collection.delete_one({'usuario': amigo, 'amigo': session['username']})
    return redirect('/dashboard')



@app.route('/places')
def places():
    if 'username' in session:
        lugares = lugares_collection.find()
        lugares_list = [lugar['nombre'] for lugar in lugares]
        promedios = calcular_promedios()
        return render_template('places.html', lugares=lugares_list, promedios=promedios)
    else:
        return redirect('/login')




@app.route('/add_place', methods=['GET', 'POST'])
def add_place():
    if 'username' in session:
        if request.method == 'POST':
            nombre = request.form['nombre']
            descripcion = request.form['descripcion']
            latitud = request.form['latitud']
            longitud = request.form['longitud']

            lugar_data = {
                'nombre': nombre,
                'descripcion': descripcion,
                'latitud': latitud,
                'longitud': longitud
            }
            lugares_collection.insert_one(lugar_data)

            return redirect('/places')
        else:
            return render_template('add_place.html')
    else:
        return redirect('/login')


@app.route('/add_interest/<string:lugar_nombre>', methods=['GET', 'POST'])
def add_interest(lugar_nombre):
    if 'username' in session:
        if request.method == 'POST':
            nombre = request.form['nombre']
            descripcion = request.form['descripcion']

            # Obtener el lugar existente
            lugar = lugares_collection.find_one({'nombre': lugar_nombre})
            if lugar:
                # Agregar el punto de interés al lugar
                punto_interes = {
                    'nombre': nombre,
                    'descripcion': descripcion
                }
                lugares_collection.update_one({'nombre': lugar_nombre}, {'$push': {'puntos_interes': punto_interes}})

            # Redirigir de regreso a la página de detalles del lugar
            return redirect(f'/place_details/{lugar_nombre}')
        else:
            return render_template('add_interest.html', lugar_nombre=lugar_nombre)
    else:
        return redirect('/login')

@app.route('/add_check/<nombre_lugar>', methods=['POST'])
def add_check(nombre_lugar):
    if 'username' in session:
        lugar = lugares_collection.find_one({'nombre': nombre_lugar})
        if lugar:
            comentario = request.form['comentario']
            puntuacion = int(request.form['puntuacion'])
            tipo = "lugar"  # Indicar que es un comentario del lugar

            fecha_hora_actual = datetime.datetime.now()

            check_data = {
                'lugar': nombre_lugar,
                'usuario': session['username'],
                'comentario': comentario,
                'puntuacion': puntuacion,
                'tipo': tipo,  # Agregar el campo "tipo" al comentario
                'fecha_hora': fecha_hora_actual.strftime("%d-%m-%Y %H:%M:%S")
            }
            checks_collection.insert_one(check_data)

    return redirect(f'/submit_comment_and_rate/{nombre_lugar}')

@app.route('/add_check_punto/<nombre_lugar>/<nombre_punto>', methods=['POST'])
def add_check_punto(nombre_lugar, nombre_punto):
    if 'username' in session:
        lugar = lugares_collection.find_one({'nombre': nombre_lugar})
        if lugar:
            punto_interes = next((punto for punto in lugar['puntos_interes'] if punto['nombre'] == nombre_punto), None)
            if punto_interes:
                comentario = request.form['comentario']
                puntuacion = int(request.form['puntuacion'])
                tipo = "punto_interes"  # Indicar que es un comentario del punto de interés

                fecha_hora_actual = datetime.datetime.now()

                check_data = {
                    'lugar': nombre_lugar,
                    'punto': nombre_punto,
                    'usuario': session['username'],
                    'comentario': comentario,
                    'puntuacion': puntuacion,
                    'tipo': tipo,  # Agregar el campo "tipo" al comentario
                    'fecha_hora': fecha_hora_actual.strftime("%d-%m-%Y %H:%M:%S")
                }
                checks_collection.insert_one(check_data)

    return redirect(f'/submit_comment_and_rate/{nombre_lugar}/{nombre_punto}')

def calcular_promedios_puntos_interes(nombre_lugar):
    lugar = lugares_collection.find_one({'nombre': nombre_lugar})
    if lugar is None or 'puntos_interes' not in lugar:
        return {}  # No hay puntos de interés o el lugar no existe

    calificaciones_puntos_interes = checks_collection.find({'lugar': nombre_lugar, 'tipo': 'punto_interes'})
    promedios_puntos_interes = {}

    for punto in lugar['puntos_interes']:
        punto_nombre = punto['nombre']
        total_puntuacion = 0
        num_calificaciones = 0

        for calificacion in calificaciones_puntos_interes:
            if calificacion['punto'] == punto_nombre:
                total_puntuacion += calificacion['puntuacion']
                num_calificaciones += 1

        if num_calificaciones > 0:
            promedio = total_puntuacion / num_calificaciones
            promedios_puntos_interes[punto_nombre] = round(promedio, 2)
        else:
            promedios_puntos_interes[punto_nombre] = 0

    return promedios_puntos_interes



@app.route('/submit_comment_and_rate/<nombre_lugar>/<punto_nombre>', methods=['GET', 'POST'])
@app.route('/submit_comment_and_rate/<nombre_lugar>', methods=['GET', 'POST'])
def submit_comment_and_rate(nombre_lugar, punto_nombre=None):
    if 'username' in session:
        lugar = lugares_collection.find_one({'nombre': nombre_lugar})

        if lugar is None:
            # Manejar el caso donde el lugar no existe
            return "El lugar no existe."

        if punto_nombre is not None:
            # Encontrar el punto de interés específico dentro del lugar
            punto_interes = next((punto for punto in lugar.get('puntos_interes', []) if punto['nombre'] == punto_nombre), None)

            if punto_interes is None:
                # Manejar el caso donde el punto de interés no existe
                return "El punto de interés no existe."

            if request.method == 'POST':
                comentario = request.form['comentario']
                puntuacion = int(request.form['puntuacion'])
                tipo = "punto_interes"

                check_data = {
                    'lugar': nombre_lugar,
                    'punto': punto_nombre,
                    'usuario': session['username'],
                    'comentario': comentario,
                    'puntuacion': puntuacion,
                    'tipo': tipo
                }
                checks_collection.insert_one(check_data)

            # Obtener comentarios y puntuaciones del lugar y del punto de interés desde la colección "checks"
            checks_lugar = checks_collection.find({'lugar': nombre_lugar, 'tipo': 'lugar'})
            checks_punto_interes = checks_collection.find({'lugar': nombre_lugar, 'punto': punto_nombre, 'tipo': 'punto_interes'})

            promedios_puntos_interes = calcular_promedios_puntos_interes(nombre_lugar)

            return render_template('place_details.html', lugar=lugar, punto=punto_interes, checks_lugar=checks_lugar, checks_punto_interes=checks_punto_interes, promedios_puntos_interes=promedios_puntos_interes)
        else:
            if request.method == 'POST':
                comentario = request.form['comentario']
                puntuacion = int(request.form['puntuacion'])
                tipo = "lugar"

                check_data = {
                    'lugar': nombre_lugar,
                    'usuario': session['username'],
                    'comentario': comentario,
                    'puntuacion': puntuacion,
                    'tipo': tipo
                }
                checks_collection.insert_one(check_data)

            # Obtener comentarios y puntuaciones del lugar y los puntos de interés desde la colección "checks"
            checks_lugar = checks_collection.find({'lugar': nombre_lugar, 'tipo': 'lugar'})
            checks_punto_interes = []

            if 'puntos_interes' in lugar:
                for punto in lugar['puntos_interes']:
                    checks_punto = checks_collection.find({'lugar': nombre_lugar, 'punto': punto['nombre'], 'tipo': 'punto_interes'})
                    checks_punto_interes.extend(checks_punto)

            promedios_puntos_interes = calcular_promedios_puntos_interes(nombre_lugar)

            return render_template('place_details.html', lugar=lugar, checks_lugar=checks_lugar, checks_punto_interes=checks_punto_interes, promedios_puntos_interes=promedios_puntos_interes)
    else:
        return redirect('/login')



@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)




