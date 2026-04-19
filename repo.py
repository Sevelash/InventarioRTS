from flask import Blueprint, render_template
from auth import module_required

repo_bp = Blueprint('repo', __name__, url_prefix='/repository')


@repo_bp.route('/')
@module_required('repository')
def index():
    return render_template('repo/index.html')
