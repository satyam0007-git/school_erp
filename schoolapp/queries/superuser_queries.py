from django.db.models import Count

from ..models import SchoolProfile, SchoolSessionRecord, Student


def get_all_school_profiles():
    return {p.school_id: p for p in SchoolProfile.objects.all()}


def get_all_session_records():
    return {
        (sr.school_id, sr.academic_session): sr
        for sr in SchoolSessionRecord.objects.all()
    }


def get_all_student_counts_by_school_session():
    return {
        (r['school_id'], r['academic_session']): r['cnt']
        for r in Student.objects.values('school_id', 'academic_session')
        .annotate(cnt=Count('id'))
    }

