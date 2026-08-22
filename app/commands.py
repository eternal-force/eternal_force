import getpass

import click

from . import services
from .exercise_catalog_seed import EXERCISE_CATALOG_SEED
from .extensions import db
from .models import User


def register(app):
    @app.cli.command("init-db")
    def init_db():
        """建立所有資料表(不會刪除既有資料)。"""
        db.create_all()
        click.echo("資料表已建立完成。")

    @app.cli.command("seed-exercise-catalog")
    def seed_exercise_catalog():
        """匯入訓練項目清單種子資料(依名稱 upsert，不會刪除既有項目)。"""
        services.seed_exercise_catalog(EXERCISE_CATALOG_SEED)
        click.echo(f"訓練項目種子資料已匯入，共 {len(EXERCISE_CATALOG_SEED)} 筆。")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    def create_admin(username):
        """建立管理者帳號(互動輸入密碼,不會顯示在畫面或指令歷史)。"""
        username = username.strip()
        if not username:
            raise click.ClickException("帳號不可為空白")
        if User.query.filter_by(username=username).first():
            raise click.ClickException(f"帳號 {username} 已存在")

        password = getpass.getpass("密碼: ")
        confirm = getpass.getpass("再次輸入密碼: ")
        if not password or len(password) < 8:
            raise click.ClickException("密碼長度至少需 8 碼")
        if password != confirm:
            raise click.ClickException("兩次輸入的密碼不一致")

        user = User(username=username, role="admin", status="active")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"管理者帳號 {username} 建立成功。")
