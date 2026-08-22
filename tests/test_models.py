from datetime import date, time

from app.models import ClassRecord, PurchaseRecord, Student


def test_summary_calculation_matches_us_4_1(app, db):
    student = Student(name="小明")
    db.session.add(student)
    db.session.commit()

    db.session.add_all(
        [
            PurchaseRecord(student_id=student.id, purchase_date=date(2026, 1, 1), quantity=10),
            PurchaseRecord(student_id=student.id, purchase_date=date(2026, 2, 1), quantity=5),
        ]
    )
    db.session.add_all(
        [
            ClassRecord(student_id=student.id, class_date=date(2026, 1, 5), class_time=time(10, 0)),
            ClassRecord(student_id=student.id, class_date=date(2026, 1, 12), class_time=time(10, 0)),
            ClassRecord(student_id=student.id, class_date=date(2026, 1, 19), class_time=time(10, 0)),
        ]
    )
    db.session.commit()
    db.session.refresh(student)

    assert student.total_purchased == 15
    assert student.total_attended == 3
    assert student.remaining == 12


def test_remaining_can_go_negative_when_overbooked(app, db):
    student = Student(name="小華")
    db.session.add(student)
    db.session.commit()

    db.session.add(PurchaseRecord(student_id=student.id, purchase_date=date(2026, 1, 1), quantity=2))
    db.session.add_all(
        [
            ClassRecord(student_id=student.id, class_date=date(2026, 1, 5), class_time=time(9, 0)),
            ClassRecord(student_id=student.id, class_date=date(2026, 1, 6), class_time=time(9, 0)),
            ClassRecord(student_id=student.id, class_date=date(2026, 1, 7), class_time=time(9, 0)),
        ]
    )
    db.session.commit()
    db.session.refresh(student)

    assert student.total_purchased == 2
    assert student.total_attended == 3
    assert student.remaining == -1
