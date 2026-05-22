from decimal import Decimal

from django.db.models import Max, Sum

from ..models import (
    ExamFee, FeePayment, FeeStructure, SchoolClass, SchoolSessionRecord, Student, Teacher,
)


def get_active_students(school, session):
    return Student.objects.filter(
        school=school, status=Student.STATUS_ACTIVE, academic_session=session,
    ).select_related('school_class')


def get_session_fee_payments(school, session):
    return FeePayment.objects.filter(school=school, academic_session=session)


def get_student_fee_payments(student, session):
    return FeePayment.objects.filter(student=student, academic_session=session)


def get_monthly_fee_structures(school_class, school, session):
    return FeeStructure.objects.filter(
        school_class=school_class,
        fee_category__school=school,
        fee_category__is_active=True,
        academic_session=session,
        frequency=FeeStructure.FREQUENCY_MONTHLY,
    )


def get_exam_fees_for_class(school, school_class, session):
    return ExamFee.objects.filter(
        school=school, school_class=school_class, academic_session=session,
    ).order_by('exam_name')


def get_classes_with_fee_structures(school, session):
    """Return classes that have a monthly fee structure configured for the given session."""
    class_ids = FeeStructure.objects.filter(
        fee_category__school=school,
        academic_session=session,
        frequency=FeeStructure.FREQUENCY_MONTHLY,
    ).values_list('school_class_id', flat=True)
    return SchoolClass.objects.filter(school=school, pk__in=class_ids).order_by('name')


def get_latest_payment_id_per_student(school, session):
    return dict(
        FeePayment.objects.filter(school=school, academic_session=session)
        .values('student_id')
        .annotate(latest_id=Max('id'))
        .values_list('student_id', 'latest_id')
    )


def get_total_paid_per_student(school, session):
    return dict(
        FeePayment.objects.filter(school=school, academic_session=session)
        .values('student_id')
        .annotate(total=Sum('amount_paid'))
        .values_list('student_id', 'total')
    )


def get_session_record(school, session):
    return SchoolSessionRecord.objects.filter(school=school, academic_session=session).first()


def get_teachers_for_session(school, session):
    return Teacher.objects.filter(school=school, academic_session=session).select_related('class_teacher_of')


def get_student_total_paid(student, session):
    result = FeePayment.objects.filter(
        student=student, academic_session=session,
    ).aggregate(t=Sum('amount_paid'))
    return result['t'] or Decimal('0.00')
