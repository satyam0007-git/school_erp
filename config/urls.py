from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from schoolapp import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Superuser
    path('super/', views.super_dashboard, name='super_dashboard'),
    path('super/settings/', views.super_settings, name='super_settings'),
    path('super/schools/add/', views.school_add, name='school_add'),
    path('super/schools/<int:pk>/edit/', views.school_edit, name='school_edit'),
    path('super/schools/<int:pk>/delete/', views.school_delete, name='school_delete'),
    path('super/users/add/', views.user_add, name='user_add'),
    path('super/users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('super/school-fee/', views.super_school_fee_dashboard, name='super_school_fee_dashboard'),
    path('super/schools/<int:school_pk>/collect-fee/', views.super_collect_fee, name='super_collect_fee'),
    path('super/schools/<int:pk>/promote/', views.super_promote_school, name='super_promote_school'),

    # Subscriptions
    path('super/plans/', views.super_plans_dashboard, name='super_plans_dashboard'),
    path('super/plans/add/', views.super_plan_add, name='super_plan_add'),
    path('super/plans/<int:pk>/edit/', views.super_plan_edit, name='super_plan_edit'),
    path('super/plans/<int:pk>/delete/', views.super_plan_delete, name='super_plan_delete'),

    # School
    path('school/', views.school_dashboard, name='school_dashboard'),

    # Admission
    path('school/admission/', views.student_list, name='student_list'),
    path('school/admission/new/', views.student_create, name='student_create'),
    path('school/admission/<int:pk>/edit/', views.student_edit, name='student_edit'),
    path('school/admission/<int:pk>/delete/', views.student_delete, name='student_delete'),
    path('school/admission/<int:pk>/promote/', views.student_promote, name='student_promote'),
    path('school/admission/<int:pk>/fail/', views.student_fail, name='student_fail'),
    path('school/admission/<int:pk>/transfer/', views.student_transfer, name='student_transfer'),
    path('school/admission/bulk-upload/', views.admission_bulk_upload, name='admission_bulk_upload'),
    path('school/admission/bulk-upload/template/', views.admission_bulk_template, name='admission_bulk_template'),
    path('school/admission/bulk-upload/errors/', views.admission_bulk_errors_download, name='admission_bulk_errors_download'),
    path('school/admission/bulk-upload/<int:pk>/success/', views.admission_bulk_success_download, name='admission_bulk_success_download'),

    # Fee Submission
    path('school/fees/', views.payment_dashboard, name='payment_dashboard'),
    path('school/fees/export/', views.payment_dashboard_export, name='payment_dashboard_export'),
    path('school/fees/print/', views.payment_dashboard_print, name='payment_dashboard_print'),
    path('school/fees/collect/', views.payment_create, name='payment_create'),
    path('school/fees/<int:pk>/', views.payment_detail, name='payment_detail'),
    path('school/fees/<int:pk>/edit/', views.payment_edit, name='payment_edit'),
    path('school/fees/ajax/fee-structure/', views.student_fee_structure_ajax, name='student_fee_structure_ajax'),
    path('school/fees/ajax/lump-sum-preview/', views.lump_sum_preview_ajax, name='lump_sum_preview_ajax'),

    # Configuration
    path('school/config/', views.config_view, name='config_view'),

    # WhatsApp Reminders
    path('school/whatsapp/', views.whatsapp_dashboard, name='whatsapp_dashboard'),
    path('school/whatsapp/send/', views.whatsapp_send, name='whatsapp_send'),
    path('school/whatsapp/announce/', views.whatsapp_announce, name='whatsapp_announce'),
    path('school/whatsapp/templates/', views.whatsapp_templates_debug, name='whatsapp_templates_debug'),

    # Announcement
    path('school/announcement/', views.announcement_dashboard, name='announcement_dashboard'),

    # Notifications (Admin)
    path('school/notifications/', views.notification_list, name='notification_list'),
    path('school/notifications/new/', views.notification_create, name='notification_create'),
    path('school/notifications/<int:pk>/edit/', views.notification_edit, name='notification_edit'),
    path('school/notifications/<int:pk>/delete/', views.notification_delete, name='notification_delete'),
    path('school/notifications/<int:pk>/toggle-publish/', views.notification_toggle_publish, name='notification_toggle_publish'),

    # Student Portal
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/receipt/<int:pk>/', views.student_payment_detail, name='student_payment_detail'),

    # Reports
    path('school/reports/', views.report_dashboard, name='report_dashboard'),
    path('school/reports/admissions/export/', views.report_admissions_export, name='report_admissions_export'),
    path('school/reports/admissions/print/', views.report_admissions_print, name='report_admissions_print'),
    path('school/reports/fees/export/', views.report_fees_export, name='report_fees_export'),
    path('school/reports/fees/print/', views.report_fees_print, name='report_fees_print'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
