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
        """從 Excel 期初匯入學生、購買堂數、已使用堂數與目前教練，有填手機者一併建立登入帳號。"""
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
        no_account = [d["name"] for _n, d in rows if not d["username"]]
        click.echo(f"將建立 {len(rows) - len(no_account)} 個學生帳號(帳號與初始密碼皆為手機號碼，首次登入須修改密碼)")
        if no_account:
            click.echo("未填手機、不建立帳號：" + "、".join(no_account))
        per_coach = {}
        for _n, d in rows:
            if d["coach_name"]:
                stats = per_coach.setdefault(d["coach_name"], {"total": 0, "opening": 0, "assigned": 0})
                stats["total"] += 1
                stats["opening"] += 1 if d["used"] > 0 else 0
                stats["assigned"] += 1 if d["username"] else 0
        for coach_name, stats in sorted(per_coach.items()):
            click.echo(
                f"教練「{coach_name}」：{stats['total']} 位學生"
                f"(建立初始匯入上課紀錄 {stats['opening']} 位、設為帳號所屬教練 {stats['assigned']} 位)"
            )
        no_coach_account = [d["name"] for _n, d in rows if d["coach_name"] and d["used"] == 0 and not d["username"]]
        if no_coach_account:
            click.echo("已使用堂數為 0 且未建立帳號，目前教練無法生效(所有教練可見)：" + "、".join(no_coach_account))
        unassigned = [d["name"] for _n, d in rows if not d["coach_name"]]
        if unassigned:
            click.echo("已使用堂數為 0、未填目前教練(所有教練可見)：" + "、".join(unassigned))
        if not commit:
            click.echo("目前只做檢查；確認無誤後加上 --commit 正式寫入")
            return
        importer.import_rows(rows)
        click.echo("匯入完成")

    @app.cli.command("backfill-account-coaches")
    @click.option("--commit", is_flag=True, help="確認無誤後正式寫入資料庫(未加則只列出將要設定的內容)")
    def backfill_account_coaches(commit):
        """依學生上課紀錄的教練，預設學生帳號的所屬教練(只新增、不移除既有設定)。"""
        changes, skipped = services.backfill_account_coaches_from_classes(commit=commit)

        def names(coaches):
            return "、".join(c.name or c.username for c in coaches)

        for account, coaches in changes:
            click.echo(f"{account.username}（{account.name or '-'}）：新增所屬教練 {names(coaches)}")
        for account, coaches in skipped:
            click.echo(f"{account.username}（{account.name or '-'}）：略過已停用教練 {names(coaches)}")
        if not changes:
            click.echo("沒有需要補設的帳號")
            return
        click.echo(f"共 {len(changes)} 個學生帳號需補設所屬教練")
        if not commit:
            click.echo("目前只做檢查；確認無誤後加上 --commit 正式寫入")
            return
        click.echo("已寫入")

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
