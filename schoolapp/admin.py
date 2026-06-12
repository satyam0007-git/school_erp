from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    AdmissionBulkUploadHistory, FeeCategory, FeePayment, FeeStructure,
    School, SchoolClass, SchoolProfile, Student, User,
)

admin.site.register(School)
admin.site.register(User, UserAdmin)
admin.site.register(SchoolProfile)
admin.site.register(SchoolClass)
admin.site.register(FeeCategory)
admin.site.register(FeeStructure)
admin.site.register(Student)
admin.site.register(FeePayment)
admin.site.register(AdmissionBulkUploadHistory)
