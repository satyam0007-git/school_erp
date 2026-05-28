import re
from decimal import Decimal

from django.db.models import Count, Sum

from ..models import (
    School, SchoolBillingPayment, SchoolProfile, SchoolSessionRecord, Student, User,
)


def get_all_school_profiles():
    return {p.school_id: p for p in SchoolProfile.objects.all()}


def get_all_session_records():
    return {
        (sr.school_id, sr.academic_session): sr
        for sr in SchoolSessionRecord.objects.all()
    }


def get_active_student_counts_by_school_session():
    return {
        (r['school_id'], r['academic_session']): r['cnt']
        for r in Student.objects.filter(status=Student.STATUS_ACTIVE)
        .values('school_id', 'academic_session').annotate(cnt=Count('id'))
    }


def get_all_student_counts_by_school_session():
    return {
        (r['school_id'], r['academic_session']): r['cnt']
        for r in Student.objects.values('school_id', 'academic_session')
        .annotate(cnt=Count('id'))
    }


def get_school_billed_sessions(school):
    return set(
        SchoolBillingPayment.objects.filter(school=school)
        .values_list('academic_session', flat=True).distinct()
    )


def get_school_billing_paid_total(school, session):
    result = SchoolBillingPayment.objects.filter(
        school=school, academic_session=session,
    ).aggregate(t=Sum('amount_paid'))
    return result['t'] or Decimal('0.00')
