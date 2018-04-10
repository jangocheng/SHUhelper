from flask import Flask, request, jsonify, Blueprint
from flask.views import MethodView
from datetime import datetime
from flask_login import login_required, current_user
from UHE.extensions import db
import requests
from .models import User, Room, Order
from functools import reduce
ces = Blueprint('ces', __name__)


def render_room_info(room, orders):
    schedule = [1 for i in range(13)]
    for order in orders:
        for i in range(order.start-1, order.end):
            schedule[i] = 0
    return {
        'id': room.id,
        'name': room.name,
        'schedule': schedule
    }


def render_rooms_info(rooms, orders):
    return [render_room_info(room, filter(lambda x:x.room_id == room.id, orders)) for room in rooms]


def cal_restrict(orders):
    used = reduce(lambda x, y: x + (y.end-y.start+1), orders, 0)
    return 4 - used


def check_restrict(order, user_id):
    orders = Order.query.filter_by(date=order.date, user_id=user_id).all()
    restrict = cal_restrict(orders)
    return restrict >= (order.end-order.start + 1)


@ces.route('/rooms/', methods=['GET'])
@login_required
def get_rooms():
    now = datetime.now()
    timestamp = request.args.get('timestamp', datetime(
        now.year, now.month, now.day).timestamp(), int)
    rooms = Room.query.filter_by(available=True).all()
    orders = Order.query.filter_by(
        date=datetime.fromtimestamp(timestamp)).all()
    user_orders = filter(lambda x: x.user_id == current_user.id, orders)
    restrict = cal_restrict(user_orders)
    return jsonify(rooms=render_rooms_info(rooms, orders), restrict=restrict)


def check_room_available(order):
    orders = Order.query.filter_by(
        room_id=order.room_id, date=order.date).all()
    for valid_order in orders:
        if valid_order.end < order.start or order.end < valid_order.start:
            continue
        else:
            return False
    return True


class OrderAPI(MethodView):
    decorators = [login_required]

    def get(self, order_id):
        if order_id is None:
            orders_type = request.args.get('type', 'personal')
            if orders_type == 'personal':
                orders = Order.query.filter_by(
                    user_id=current_user.id).order_by(Order.date.desc()).all()
                return jsonify(orders=[order.to_json() for order in orders])
        else:
            order = Order.query.filter_by(id=order_id).first()
            return jsonify(order=order.to_json())

    def post(self):
        now = datetime.now()
        json = request.json
        json['userID'] = current_user.id
        order = Order.from_json(json)
        if check_restrict(order, current_user.id) == False:
            return jsonify(msg='您当日借教室时长配额不足'), 400
        if check_room_available(order) == False:
            return jsonify(msg='该时间段已被占用'), 400
        timedelta = order.date - now
        if timedelta.days < 0 or timedelta.days > 3:
            return jsonify(msg='该日无法预约'), 400
        order.save()
        return jsonify(order=order.to_json())

    def delete(self, order_id):
        if order_id is None:
            return jsonify(msg="无权限"), 401
        else:
            order = Order.query.filter_by(id=order_id).first()
            if not order.user_id == current_user.id:
                return jsonify(msg="无权限"), 401
            db.session.delete(order)
            db.session.commit()
            return jsonify(success=True)

    def put(self, order_id):
        # update a single user
        pass


user_view = OrderAPI.as_view('order_api')
ces.add_url_rule('/orders/', defaults={'order_id': None},
                 view_func=user_view, methods=['GET', ])
ces.add_url_rule('/orders/', view_func=user_view, methods=['POST', ])
ces.add_url_rule('/orders/<int:order_id>', view_func=user_view,
                 methods=['GET', 'PUT', 'DELETE'])
