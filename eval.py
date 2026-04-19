from flask import Blueprint, render_template
from auth import module_required

eval_bp = Blueprint('eval', __name__, url_prefix='/evaluation')


@eval_bp.route('/')
@module_required('evaluation')
def index():
    return render_template('eval/index.html')
