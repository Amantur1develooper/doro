from django.contrib import admin
from .models import Region, Doctor, Pharmacy, Visit, VisitPhoto, VisitAudio, VisitPlan


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display  = ['name', 'code']
    search_fields = ['name']


class VisitPhotoInline(admin.TabularInline):
    model = VisitPhoto
    extra = 0
    readonly_fields = ['uploaded_at']


class VisitAudioInline(admin.TabularInline):
    model = VisitAudio
    extra = 0
    readonly_fields = ['uploaded_at']


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display   = ['full_name', 'specialty', 'institution', 'region', 'representative', 'phone']
    list_filter    = ['region', 'specialty']
    search_fields  = ['full_name', 'institution', 'phone']
    autocomplete_fields = ['region']
    raw_id_fields  = ['representative']


@admin.register(Pharmacy)
class PharmacyAdmin(admin.ModelAdmin):
    list_display  = ['name', 'address', 'region', 'representative', 'debt', 'phone']
    list_filter   = ['region']
    search_fields = ['name', 'address', 'phone']
    raw_id_fields = ['representative']


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display   = ['employee', 'visit_type', 'doctor', 'pharmacy', 'status',
                      'planned_date', 'actual_date']
    list_filter    = ['status', 'visit_type', 'planned_date']
    search_fields  = ['employee__username', 'doctor__full_name', 'pharmacy__name']
    raw_id_fields  = ['employee', 'doctor', 'pharmacy']
    date_hierarchy = 'planned_date'
    inlines        = [VisitPhotoInline, VisitAudioInline]


@admin.register(VisitPlan)
class VisitPlanAdmin(admin.ModelAdmin):
    list_display  = ['employee', 'month', 'year', 'planned_visits']
    list_filter   = ['year', 'month']
    raw_id_fields = ['employee']
