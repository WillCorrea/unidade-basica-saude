from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User, UserUbsMembership


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    pass


@admin.register(UserUbsMembership)
class UserUbsMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "ubs", "group", "active", "updated_at")
    list_filter = ("active", "group")
    search_fields = ("user__username", "ubs__name", "group__name")
