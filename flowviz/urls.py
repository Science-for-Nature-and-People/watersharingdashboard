from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),

    url(r'projects/$', views.projects, name='projects'),
    url(r'projects/(?P<project_id>[0-9]+)/$', views.project_detail, name='project_detail'),
    url(r'projects/(?P<project_id>[0-9]+)/compare/$', views.project_compare, name='project_compare'),

    # Project comparison static plot urls.
    url(r'projects/(?P<project_id>[0-9]+)/compare/pct_plot$', views.project_deficit_days_plot, name='project_pct_plot'),

    url(r'projects/(?P<project_id>[0-9]+)/compare/stats_plot$', views.project_deficit_stats_plot, name='project_stats_plot'),
    url(r'projects/(?P<project_id>[0-9]+)/compare/stats_pct_plot$', views.project_deficit_stats_pct_plot, name='project_stats_pct_plot'),

    # Project comparison data URLs
    url(r'projects/(?P<project_id>[0-9]+)/data/$', views.project_data, name='project_data'),
    url(r'projects/(?P<project_id>[0-9]+)/pct_csv/$', views.project_deficit_days_csv, name='project_deficit_days_csv'),
    url(r'projects/(?P<project_id>[0-9]+)/stats_csv/$', views.project_deficit_stats_csv, name='project_deficit_stats_csv'),
    url(r'projects/(?P<project_id>[0-9]+)/stats_pct_csv/$', views.project_deficit_stats_pct_csv, name='project_deficit_stats_pct_csv'),

    url(r'scenario/(?P<scenario_id>[0-9]+)/$', views.scenario, name='scenario'),

    # Scenario
    url(r'scenario/(?P<scenario_id>[0-9]+)/raster/(?P<attribute>[a-zA-Z_\-]+)/', views.dynamic_raster, name='scenario-dynamic-raster'),
    # Temporal Deficit Plots
    url(r'scenario/(?P<scenario_id>[0-9]+)/temporal_monthly/', views.deficit_days_plot, name='scenario-deficit-days'),
    url(r'scenario/(?P<scenario_id>[0-9]+)/temporal_annual/', views.annual_deficit_days_plot, name='scenario-deficit-days-annual'),
    # Volume Deficit Plots
    url(r'scenario/(?P<scenario_id>[0-9]+)/volume_monthly_pct/', views.deficit_stats_pct_plot, name='scenario-deficit-stats-pct'),
    url(r'scenario/(?P<scenario_id>[0-9]+)/volume_annual_pct/', views.deficit_stats_pct_plot_annual, name='scenario-deficit-stats-pct-annual'),
    url(r'scenario/(?P<scenario_id>[0-9]+)/volume_monthly/', views.deficit_stats_plot, name='scenario-deficit-stats'),
    url(r'scenario/(?P<scenario_id>[0-9]+)/volume_annual/', views.deficit_stats_plot_annual, name='scenario-deficit-stats-annual'),

    # Other Scenario URLs
    url(r'scenario/(?P<scenario_id>[0-9]+)/average/', views.right_plot, name='scenario-average'),
    url(r'scenario/(?P<scenario_id>[0-9]+)/data/', views.scenario_data, name='scenario-data'),
]
