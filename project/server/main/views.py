# project/server/main/views.py
import os
from datetime import datetime
from gettext import lngettext
from os import DirEntry

import requests
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from flask import (Blueprint, Markup, flash, jsonify, redirect,
                   render_template, request, url_for)
from project.server import db
from project.server.main.forms import ConsultaCalendarioForm, ConsultaUbsForm
from project.server.models import Template
from sqlalchemy import lateral

load_dotenv()  # take environment variables from .env.


main_blueprint = Blueprint("main", __name__)


@main_blueprint.route("/")
def home():
    return redirect(url_for("main.consulta_calendario"))


@main_blueprint.route("/consulta_ubs", methods=["GET", "POST"])
def consulta_ubs():
    form = ConsultaUbsForm(request.form)

    if form.validate_on_submit():
        cep = form.cep.data
        print('O cep digitado foi', cep)
        # monta a url para consulta dos dados do cep na API
        url = os.environ.get("API_CEP_URL")+cep.replace("-", "")
        print('A url consultada foi', url)

        headers = {
            'Authorization': 'Token token='+os.environ.get("API_CEP_TOKEN")}
        response = requests.get(url, headers=headers)

        dados_cep = response.json()

        # consulta ubs mais próximas
        lat = dados_cep.get('latitude')
        lng = dados_cep.get('longitude')
        ibge = dados_cep.get('cidade').get('ibge')
        sql = f'''
        SELECT DISTINCT TOP 10
            *,
            sqrt(square(abs(Latitude-({lat}))) + square(abs(Longitude-({lng})))) as Distance
        FROM
            [dbo].[cadastro_estabelecimentos_cnes]
        WHERE
            IBGE = LEFT({ibge}, 6) AND
            sqrt(square(abs(Latitude-({lat}))) + square(abs(Longitude-({lng})))) < 5
        ORDER BY
            Distance
        ASC
        '''

        print(sql)

        rows = []

        try:
            rows = db.engine.execute(sql)
        except:
            print('Erro executando sql', sql)

        return render_template(
            'main/resultado_consulta_ubs.html',
            cep=cep,
            dados_cep=dados_cep,
            rows=rows,
            sql=sql
        )

    return render_template("main/consulta_ubs.html", form=form)


@main_blueprint.route("/sobre")
def sobre():
    return render_template("main/sobre.html")


@main_blueprint.route("/adolescentes")
def adolescentes():
    return render_template("calendario/adolescentes.html")


@main_blueprint.route("/adultos")
def adultos():
    return render_template("calendario/adultos.html")


@main_blueprint.route("/criancas")
def criancas():
    return render_template("calendario/criancas.html")


@main_blueprint.route("/gestantes")
def gestantes():
    return render_template("calendario/gestantes.html")


@main_blueprint.route("/idosos")
def idosos():
    return render_template("calendario/idosos.html")


@main_blueprint.route("/consulta_calendario", methods=["GET", "POST"])
def consulta_calendario():
    form = ConsultaCalendarioForm(request.form)

    if form.validate_on_submit():
        data_nascimento = form.data_nascimento.data
        is_gestante = form.is_gestante.data
        hoje = datetime.today().date()
        anos = relativedelta(hoje, data_nascimento).years

        # mensagem de alerta para as gestantes
        if is_gestante == '1':
            mensagem = '''
            Atenção!  De acordo com o Ministério da Saúde, há vacinas que gestantes não podem tomar. Verifique com seu médico.
            '''
            mensagem = Markup(mensagem)
            flash(mensagem, "danger")

        # criança - >=0 and 4 anos
        if anos >= 0 and anos <= 4:
            nome_template = 'crianças'

        if anos > 4 and anos < 9:
            # criança sem vacina - +4 e <9
            mensagem = '''
            Para essa faixa etária não há vacinas disponibilizadas obrigatórias de acordo com o ministério da Saúde.
            </br>
            Dicas:
            </br>
            - Consulte o posto de vacinação mais próximo para verificar se há campanhas locais de imunização.</br>
            - Veja o calendário anterior se há alguma vacina faltante para imunização completa no quadro abaixo.
            '''
            mensagem = Markup(mensagem)
            flash(mensagem, "warning")
            nome_template = 'crianças'

        # adolescente - 9 a 19 anos
        if anos >= 9 and anos <= 19:
            nome_template = 'adolescentes'

        # adulto - 20 A 59 anos
        if anos >= 20 and anos <= 59:
            nome_template = 'adultos'

        # idoso += 60
        if anos >= 60:
            nome_template = 'idosos'

        # buscar no banco de dados o template correspondente a essa idade
        template = Template.query.filter_by(nome=nome_template).first()
        # usar o campo caminho da tabela template, para renderizar o
        # conteúdo correspondente
        return render_template(template.get_caminho(), is_gestante=is_gestante)

    return render_template("main/home.html", form=form)


# formulário para consulta de unidades de saúde
@main_blueprint.route("/consulta_ubs_por_endereco", methods=["GET"])
def consulta_ubs_por_endereco():
    return render_template("main/ubs_formulario_endereco.html")


# criar uma "API" que retorna as UFs onde existem unidades de saúde
@main_blueprint.route("/ubs_uf", methods=["GET"])
def ubs_ufs():
    sql = f'''
        SELECT
            DISTINCT UF
        FROM
            univesp.dbo.unidades_vacinacao
        ORDER BY
            UF
        ;
    '''

    rows = []

    try:
        rows = db.engine.execute(sql)
    except:
        print('Erro executando sql', sql)

    response = jsonify({'result': [dict(row) for row in rows]})
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


# criar uma "API" que retorna as cidades onde existem unidades de saúde
# de acordo com a UF de entrada
@main_blueprint.route("/ubs_cidades", methods=["GET"])
def ubs_cidades():
    uf = request.args.get('uf', default='SP', type=str)
    sql = f'''
        SELECT DISTINCT
            MUNICIPIO
        FROM
            univesp.dbo.unidades_vacinacao
        WHERE 
            UF = '{uf}'
        ORDER BY 
            MUNICIPIO
    '''

    rows = []

    try:
        rows = db.engine.execute(sql)
    except:
        print('Erro executando sql', sql)

    response = jsonify({'result': [dict(row) for row in rows]})
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


# criar uma "API" que retorna os bairros onde existem unidades de saúde
# de acordo com a UF e o Município
@main_blueprint.route("/ubs_bairros", methods=["GET"])
def ubs_bairros():
    uf = request.args.get('uf', default='SP', type=str)
    municipio = request.args.get(
        'municipio', default='SAO PAULO', type=str)
    sql = f'''
        SELECT DISTINCT
            BAIRRO
        FROM
            univesp.dbo.unidades_vacinacao
        WHERE 
            UF = '{uf}' AND 
            MUNICIPIO = '{municipio}'
        ORDER BY 
            BAIRRO
    '''

    rows = []

    try:
        rows = db.engine.execute(sql)
    except:
        print('Erro executando sql', sql)

    response = jsonify({'result': [dict(row) for row in rows]})
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


# criar uma "API" que retorna as ubs de acordo com a UF, Munício e Bairro
# http://127.0.0.1:5000/ubs_lista?uf=RS&municipio=ALECRIM&bairro=CENTRO
@main_blueprint.route("/ubs_lista", methods=["GET"])
def ubs_lista():
    uf = request.args.get('uf', default='SP', type=str)
    municipio = request.args.get(
        'municipio', default='SAO PAULO', type=str)
    bairro = request.args.get('bairro', default='PENHA', type=str)

    sql = f'''
        SELECT
            UF,
            MUNICIPIO,
            ESTABELECIMENTO,
            LOGRADOURO,
            NUMERO,
            BAIRRO
        FROM
            univesp.dbo.unidades_vacinacao
        WHERE 
            UF = '{uf}' AND
            MUNICIPIO = '{municipio}' AND
            BAIRRO	= '{bairro}'
    '''

    if bairro == 'Todos':
        sql = f'''
            SELECT
                UF,
                MUNICIPIO,
                ESTABELECIMENTO,
                LOGRADOURO,
                NUMERO,
                BAIRRO
            FROM
                univesp.dbo.unidades_vacinacao
            WHERE 
                UF = '{uf}' AND
                MUNICIPIO = '{municipio}'
        '''

    rows = []

    try:
        rows = db.engine.execute(sql)
    except:
        print('Erro executando sql', sql)

    return render_template(
        'main/resultado_consulta_ubs_por_municipio_bairro.html',
        uf=uf,
        municipio=municipio,
        bairro=bairro,
        rows=rows,
    )
