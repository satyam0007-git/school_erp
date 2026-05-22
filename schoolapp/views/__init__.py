from .auth_views import dashboard, login_view, logout_view, school_dashboard
from .config_views import config_view
from .fee_views import (
    lump_sum_preview_ajax,
    payment_create,
    payment_dashboard,
    payment_dashboard_export,
    payment_dashboard_print,
    payment_detail,
    payment_edit,
    student_fee_structure_ajax,
)
from .report_views import (
    report_admissions_export,
    report_admissions_print,
    report_dashboard,
    report_fees_export,
    report_fees_print,
)
from .salary_views import salary_dashboard, salary_detail, salary_pay
from .student_views import (
    admission_bulk_errors_download,
    admission_bulk_template,
    admission_bulk_upload,
    student_create,
    student_delete,
    student_edit,
    student_fail,
    student_list,
    student_promote,
    student_transfer,
)
from .superuser_views import (
    school_add,
    school_delete,
    school_edit,
    super_collect_fee,
    super_dashboard,
    super_promote_school,
    super_school_fee_dashboard,
    super_settings,
    user_add,
    user_delete,
)
from .teacher_views import (
    teacher_create,
    teacher_delete,
    teacher_edit,
    teacher_list,
    teacher_promote,
)
from .whatsapp_views import (
    announcement_dashboard,
    whatsapp_announce,
    whatsapp_dashboard,
    whatsapp_send,
    whatsapp_templates_debug,
)

__all__ = [
    'dashboard', 'login_view', 'logout_view', 'school_dashboard',
    'config_view',
    'lump_sum_preview_ajax', 'payment_create', 'payment_dashboard',
    'payment_dashboard_export', 'payment_dashboard_print', 'payment_detail',
    'payment_edit', 'student_fee_structure_ajax',
    'report_admissions_export', 'report_admissions_print', 'report_dashboard',
    'report_fees_export', 'report_fees_print',
    'salary_dashboard', 'salary_detail', 'salary_pay',
    'admission_bulk_errors_download', 'admission_bulk_template', 'admission_bulk_upload',
    'student_create', 'student_delete', 'student_edit', 'student_fail',
    'student_list', 'student_promote', 'student_transfer',
    'school_add', 'school_delete', 'school_edit', 'super_collect_fee',
    'super_dashboard', 'super_promote_school', 'super_school_fee_dashboard',
    'super_settings', 'user_add', 'user_delete',
    'teacher_create', 'teacher_delete', 'teacher_edit', 'teacher_list', 'teacher_promote',
    'announcement_dashboard', 'whatsapp_announce', 'whatsapp_dashboard',
    'whatsapp_send', 'whatsapp_templates_debug',
]
