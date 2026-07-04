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
from .student_views import (
    admission_bulk_errors_download,
    admission_bulk_success_download,
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
    super_renew_school,
    super_school_fee_dashboard,
    super_settings,
    user_add,
    user_delete,
    super_plans_dashboard,
    super_plan_add,
    super_plan_edit,
    super_plan_delete,
)
from .whatsapp_views import (
    announcement_dashboard,
    whatsapp_announce,
    whatsapp_dashboard,
    whatsapp_send,
    whatsapp_templates_debug,
)
from .notification_views import (
    notification_list,
    notification_create,
    notification_edit,
    notification_delete,
    notification_toggle_publish,
)
from .student_portal_views import (
    student_dashboard,
    student_payment_detail,
)


__all__ = [
    'dashboard', 'login_view', 'logout_view', 'school_dashboard',
    'config_view',
    'lump_sum_preview_ajax', 'payment_create', 'payment_dashboard',
    'payment_dashboard_export', 'payment_dashboard_print', 'payment_detail',
    'payment_edit', 'student_fee_structure_ajax',
    'report_admissions_export', 'report_admissions_print', 'report_dashboard',
    'report_fees_export', 'report_fees_print',
    'admission_bulk_errors_download', 'admission_bulk_success_download',
    'admission_bulk_template', 'admission_bulk_upload',
    'student_create', 'student_delete', 'student_edit', 'student_fail',
    'student_list', 'student_promote', 'student_transfer',
    'school_add', 'school_delete', 'school_edit', 'super_collect_fee',
    'super_dashboard', 'super_renew_school', 'super_school_fee_dashboard',
    'super_settings', 'user_add', 'user_delete',
    'super_plans_dashboard', 'super_plan_add', 'super_plan_edit', 'super_plan_delete',
    'announcement_dashboard', 'whatsapp_announce', 'whatsapp_dashboard',
    'whatsapp_send', 'whatsapp_templates_debug',
    'notification_list', 'notification_create', 'notification_edit',
    'notification_delete', 'notification_toggle_publish',
    'student_dashboard', 'student_payment_detail',
]

