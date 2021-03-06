from flask import request, abort, g
from flask.json import jsonify
from . import registration_blueprint, token_auth
from .models import Uni, Registration, Mascot
from .helpers import send_registration_success_mail
from app.user import groups_required
from app.user.models import User
from app.oauth2 import oauth
from app.db import db
import json

@registration_blueprint.route('/api/unis')
@oauth.require_oauth('uni_list')
def api_unis():
    unis = {uni.id: uni.name for uni in Uni.query.all()}
    return jsonify(unis)

@registration_blueprint.route('/api/registration', methods=['GET', 'POST'])
@oauth.require_oauth('registration')
def api_register():
    user = request.oauth.user
    other_username = None
    if request.headers.get('Content-Type') == 'application/json':
        req = request.get_json()
        if 'username' in req:
            other_username = req['username']
    elif request.args.get('username'):
        other_username = request.args.get('username')
    if (user.is_admin or 'orga' in user.groups) and other_username:
        user = User.get(other_username)
        if not user:
            return "Username unknown", 409
    registration = Registration.query.filter_by(username=user.username).first()
    if request.method == 'POST' \
        and request.headers.get('Content-Type') == 'application/json':
        req = request.get_json()
        if not registration:
            registration = Registration()

        registration.username = user.username
        registration.uni_id = req['uni_id']
        registration.blob = json.dumps(req['data'])
        # set registration to False on the first write
        registration.confirmed = registration.confirmed or False
        db.session.add(registration)
        db.session.commit()
        send_registration_success_mail(user)
        return "OK"

    if not registration:
        return "", 204

    return jsonify(
        uni_id = registration.uni_id,
        confirmed = registration.confirmed,
        data = registration.blob,
    )

@registration_blueprint.route('/api/priorities', methods=['GET', 'POST'])
@token_auth.login_required
def api_registration_priorities():
    """
    POST: Send a list of confirmed registration IDs in the following format
        {
            "confirmed": [
                id1, id2, id3,...
            ]
        }

    GET:
        {
            "uni": <uni name>,
            "registrations": [
                {
                    "mail": <user email>,
                    "name": <username>,
                    "priority": <null or number>,
                    "reg_id": <registration id>
                }
            ]
        }
    """
    if request.method == 'POST' \
        and request.headers.get('Content-Type') == 'application/json':
        req = request.get_json()
        if not req:
            abort(403)
            return ''

        # Get a list of all registrations by this uni
        registrations = {reg.id: reg for reg in Registration.query.filter_by(uni_id = g.uni.id)}

        # Set the priorities according to the order they are given in in the confirmed list
        for priority, reg_id in enumerate(req['confirmed']):
            reg = registrations.pop(reg_id, None)
            if reg is None:
                raise ValueError
            reg.confirmed = True
            reg.priority = priority
            db.session.add(reg)

        # Set all remaining priorities as unconfirmed
        for reg in registrations.values():
            reg.confirmed = False
            reg.priority = None
            db.session.add(reg)

        db.session.commit()
        return "OK"

    # GET requiest: return list of registrations ordered by priority
    registrations = sorted(Registration.query.filter_by(uni_id = g.uni.id), key=lambda r: r.priority or 0)

    def format_reg(reg):
        return {
            'reg_id': reg.id,
            'name': reg.user.full_name,
            'mail': reg.user.mail,
            'priority': reg.priority
        }

    return jsonify(
            uni=g.uni.name,
            slots=g.uni.slots,
            registrations=[format_reg(reg) for reg in registrations if reg.confirmed]
                         +[format_reg(reg) for reg in registrations if not reg.confirmed]
        )

@registration_blueprint.route('/api/mascots', methods=['GET', 'POST'])
@token_auth.login_required
def api_mascots():
    if request.method == 'POST' \
        and request.headers.get('Content-Type') == 'application/json':
        req = request.get_json()
        
        mascot = Mascot(req['name'], g.uni.id)
        db.session.add(mascot)
        db.session.commit()
        return "OK"


    mascots = Mascot.query.filter_by(uni_id = g.uni.id)

    def format_masc(mascot):
        return {
            'id': mascot.id,
            'name': mascot.name,
        }

    return jsonify(
            uni=g.uni.name,
            mascots=[format_masc(masc) for masc in mascots]
        )

@registration_blueprint.route('/api/mascots/delete', methods=['GET', 'POST'])
@token_auth.login_required
def delete_mascot():
    if request.headers.get('Content-Type') == 'application/json':
        req = request.get_json()
        if 'id' in req:
            mascot_id = req['id']
    elif request.args.get('username'):
        mascot_id = request.args.get('id')
    mascot = Mascot.query.filter_by(id=mascot_id).first()
    print(mascot.uni_id)
    if(mascot.uni_id == g.uni.id):
       db.session.delete(mascot)
       db.session.commit()

    return "OK"

