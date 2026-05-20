from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import School, SchoolClass, SchoolProfile, SchoolSessionRecord, Student


class StudentPromotionTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.school = School.objects.create(name='Test School')
		SchoolProfile.objects.create(school=self.school, current_academic_session='2026-27')
		self.class_1 = SchoolClass.objects.create(school=self.school, name='Class 1')
		self.class_2 = SchoolClass.objects.create(school=self.school, name='Class 2')
		self.user = user_model.objects.create_user(
			username='school_admin',
			password='pass12345',
			role=user_model.SCHOOL_ADMIN,
			school=self.school,
		)
		self.student = Student.objects.create(
			school=self.school,
			school_class=self.class_1,
			name='Yashi',
			date_of_birth='2015-01-01',
			academic_session='2026-27',
			father_name='Ramesh',
			father_phone='1234567890',
			address='Test Address',
		)

	def test_promote_creates_new_student_and_preserves_old_record(self):
		self.client.login(username='school_admin', password='pass12345')

		response = self.client.post(reverse('student_promote', args=[self.student.pk]))

		self.assertEqual(response.status_code, 302)
		self.assertEqual(Student.objects.count(), 2)

		self.student.refresh_from_db()
		self.assertEqual(self.student.status, Student.STATUS_PROMOTED)
		self.assertEqual(self.student.school_class, self.class_1)
		self.assertEqual(self.student.academic_session, '2026-27')

		promoted_student = Student.objects.exclude(pk=self.student.pk).get()
		self.assertEqual(promoted_student.status, Student.STATUS_ACTIVE)
		self.assertEqual(promoted_student.school_class, self.class_2)
		self.assertEqual(promoted_student.academic_session, '2027-28')
		self.assertEqual(promoted_student.name, self.student.name)
		self.assertEqual(promoted_student.father_name, self.student.father_name)
		self.assertEqual(promoted_student.father_phone, self.student.father_phone)
		self.assertEqual(promoted_student.address, self.student.address)


class SuperuserSchoolRenewalTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.superuser = user_model.objects.create_user(
			username='super',
			password='pass12345',
			role=user_model.SUPERUSER,
		)
		self.school = School.objects.create(name='Renewal School')
		self.profile = SchoolProfile.objects.create(
			school=self.school,
			current_academic_session='2026-27',
			billing_start_month='april',
			billing_end_month='march',
			session_start_month='april',
			session_end_month='march',
		)
		SchoolSessionRecord.objects.create(
			school=self.school,
			academic_session='2026-27',
			session_start_month='april',
			session_end_month='march',
			billing_start_month='april',
			billing_end_month='march',
		)

	def test_superuser_renew_creates_new_session_record(self):
		self.client.login(username='super', password='pass12345')

		response = self.client.post(reverse('super_promote_school', args=[self.school.pk]))

		self.assertEqual(response.status_code, 302)
		self.profile.refresh_from_db()
		self.assertEqual(self.profile.current_academic_session, '2027-28')
		self.assertEqual(SchoolSessionRecord.objects.filter(school=self.school).count(), 2)
		self.assertTrue(SchoolSessionRecord.objects.filter(school=self.school, academic_session='2026-27').exists())
		self.assertTrue(SchoolSessionRecord.objects.filter(school=self.school, academic_session='2027-28').exists())
