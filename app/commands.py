import getpass

import click

from . import importer, services
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

    @app.cli.command("export-import-template")
    @click.argument("path", default="學生堂數匯入範本.xlsx")
    def export_import_template(path):
        """產生學生堂數期初匯入的 Excel 範本。"""
        importer.build_template(path)
        click.echo(f"已產生匯入範本：{path}")

    @app.cli.command("import-students")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False))
    @click.option("--commit", is_flag=True, help="全部檢查通過後正式寫入資料庫(未加則只檢查)")
    def import_students(path, commit):
        """從 Excel 期初匯入學生、購買堂數與已使用堂數。"""
        rows, errors = importer.read_rows(path)
        for row_no, message in errors:
            click.echo(f"第 {row_no} 列：{message}", err=True)
        if errors:
            raise click.ClickException(f"共 {len(errors)} 列有誤，整批未寫入，請修正後重新執行")
        if not rows:
            raise click.ClickException("檔案內沒有可匯入的資料列")

        total_qty = sum(d["quantity"] for _n, d in rows)
        total_used = sum(d["used"] for _n, d in rows)
        click.echo(f"檢查通過：{len(rows)} 位學生，購買 {total_qty} 堂、期初扣抵 {total_used} 堂、剩餘 {total_qty - total_used} 堂")
        if not commit:
            click.echo("目前只做檢查；確認無誤後加上 --commit 正式寫入")
            return
        importer.import_rows(rows)
        click.echo("匯入完成")

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
