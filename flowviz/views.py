from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse, HttpResponseBadRequest
from django.core import serializers
from django.views.generic import View
from django.core.urlresolvers import reverse

from rest_framework.views import APIView
from rest_framework import generics

from models import Project, ProjectScenarioRelationship, ProjectCropMixRelationship
from serializers import ProjectScenarioRelationshipSerializer, ProjectCropMixRelationshipSerializer
from forms import ProjectScenarioRelationshipForm, ProjectForm, ProjectCropMixRelationshipForm
from forms import HUCRegionFormSet, GISLayerFormSet

from scenarios.models import Scenario
from scenarios.forms import ScenarioForm, CyclicTargetElementFormSet

from econ.views import read_crop_mix, get_bls_key
from econ.models import ConsumerPriceIndexData
import econ.plots

from utils.views import EditObjectView, NewObjectView

from datafiles.forms import FileUploadForm

from waterkit.flow import plotting, analysis
from waterkit.flow.analysis import CFS_TO_AFD

import waterkit.econ.analysis as econ_analysis

from utils.mpl import new_figure, plot_to_response, to_percent

from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from pylab import figure
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import matplotlib.colors
from matplotlib.ticker import FuncFormatter

from bokeh.embed import components
from bokeh.resources import CDN

from datetime import datetime
from functools import partial

import pandas as pd

import json

DEFAULT_PLOT_STYLE = 'ggplot'

import logging
logger = logging.getLogger(__name__)

def index(request):
    return render(request, 'flowviz/index.django.html')

def projects(request):
    projects = Project.objects.filter(show_project=True).order_by('name')
    return render(request, 'flowviz/projects.django.html',{
        'projects': projects,
        'title': 'Projects',
        'year': datetime.now().year,
    })

class ProjectDetailView(View):

    class EconPlots(object):
        def __init__(self, title, left_plot, right_plot):
            self.title = title
            self.left_plot_script, self.left_plot_div = components(left_plot, CDN)
            self.right_plot_script, self.right_plot_div = components(right_plot, CDN)

    def _plot_crop_mix(self, crop_mix):
        crop_mix, data, years, commodities = read_crop_mix(crop_mix.id)
        groups = [g.as_cropgroup() for g in crop_mix.cropmixgroup_set.all()]
        if groups:
            revenue_table = data.get_derived_table("Revenue", groups)
            revenue_table_cpi = econ_analysis.adjust_cpi(
                revenue_table,
                get_bls_key(),
                crop_mix.cpi_adjustment_year,
                ConsumerPriceIndexData.as_dataframe()
            )
            niwr_table = data.get_derived_table("NIWR", groups)
            labor_table = data.get_derived_table("Labor", groups)
            revenue_af_plot = econ.plots.plot_revenue_af_table(revenue_table_cpi, niwr_table)
            labor_plot = econ.plots.plot_labor_table(labor_table)
            return self.EconPlots(crop_mix.name, revenue_af_plot, labor_plot)
        else:
            # Just do the best we can with what we have and return only the
            # acreages.
            acre_plot = econ.plots.plot_acres(data, groups)
            acre_fraction_plot = econ.plots.plot_acre_fractions(data, groups)
            return self.EconPlots(crop_mix.name, acre_plot, acre_fraction_plot)


    def get(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)

        huc_scale = project.huc_scale
        if not huc_scale:
            huc_scale = ""
        huc_regions = map(lambda r: r.hucid, project.hucregion_set.all())

        usgs_ids = []
        point_locations = []
        for s in project.scenarios.all():
            if s.gage_location:
                usgs_ids.append(s.gage_location.identifier)
            elif s.excel_file.longitude and s.excel_file.latitude:
                point_locations.append({
                    "name": s.excel_file.name,
                    "longitude": float(s.excel_file.longitude),
                    "latitude": float(s.excel_file.latitude),
                    "url": reverse("view-file", args=[s.excel_file.id])
                })

        gis_layers = map(lambda r: r.url, project.gislayer_set.all())

        # Crop mix data.
        crop_mix_plots = map(self._plot_crop_mix, project.crop_mixes.all())

        context = {
            'project': project,
            'title': project.name,
            'year': datetime.now().year,
            'huc_scale': huc_scale,
            'huc_regions': json.dumps(huc_regions),
            'usgs_gages': json.dumps(usgs_ids),
            'gis_layers': json.dumps(gis_layers),
            'crop_mix_plots': crop_mix_plots,
            'add_scenario_form': ProjectScenarioRelationshipForm(),
            'add_cropmix_form': ProjectCropMixRelationshipForm(),
            'point_locations': json.dumps(point_locations)
        }
        return render(request, 'flowviz/project.django.html', context)

class ProjectEditView(EditObjectView):
    template_name = "flowviz/project_edit.django.html"
    model = Project
    form = ("project", ProjectForm)
    formsets = {
        "huc_formset": HUCRegionFormSet,
        "gis_formset": GISLayerFormSet,
    }
    title = "Edit project"
    url_name = "project-edit"
    redirect_url_name = "project_detail"
    redirect_parameter_name = "project_id"

class NewProjectView(NewObjectView):
    template_name = "flowviz/project_edit.django.html"
    model = Project
    form = ("project", ProjectForm)
    formsets = {
        "huc_formset": HUCRegionFormSet,
        "gis_formset": GISLayerFormSet,
    }
    title = "New Project"
    url_name = "project-new"
    redirect_url_name = "project_detail"
    redirect_parameter_name = "project_id"

class ProjectNewScenarioView(View):
    template_name = "scenarios/scenario_edit.django.html"
    def get(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        form = ScenarioForm(prefix="scenario")
        target_formset = CyclicTargetElementFormSet(prefix="target_formset")
        return render(request, self.template_name, {
            "project": project,
            "title": "Create a Scenario",
            "year": datetime.now().year,
            "form": form,
            "target_formset": target_formset,
            "upload_form": FileUploadForm(),
            "post_url": reverse("project-new-scenario",
                kwargs = { "project_id": project.id, }
            ),
        })

    def post(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        form = ScenarioForm(request.POST, prefix="scenario")
        target_formset = CyclicTargetElementFormSet(request.POST,
            prefix="target_formset")
        if form.is_valid() and target_formset.is_valid():
            scenario = form.save()
            target_formset.instance = scenario
            target_formset.save()
            relationship = ProjectScenarioRelationship(
                project = project, scenario=scenario
            )
            relationship.save()
            return redirect("project_detail", project_id=project.id)
        return render(request, self.template_name, {
            "project": project,
            "title": "Create a Scenario",
            "year": datetime.now().year,
            "form": form,
            "target_formset": target_formset,
            "upload_form": FileUploadForm(),
            "post_url": reverse("project-new-scenario",
                kwargs = { "project_id": project.id, }
            ),
        })

def project_compare(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    context = {
        'project': project,
    }
    return render(request, 'flowviz/project_compare.django.html', context)

def __get_deficit_days_comparison(project, analysis_f, index_name):
    """
    Get the temporal deficit comparison for a project.

    analysis_f : f(data, gap_attribute_name, target_attribute_name)
        The function that returns the annual temporal information.
    index_name : string
        The name to use for the resulting DataFrame's index.
    """
    datasets = []
    names = []
    for scenario in project.scenarios.all():
    	#try:
    	    data = scenario.get_data()
    	    attribute_name = scenario.get_gap_attribute_name()
    	    target_attribute_name = scenario.get_target_attribute_name()
    	    data_pct = analysis_f(data, attribute_name, target_attribute_name)
    	    data_pct.index.name = index_name
    	    datasets.append(data_pct)
    	    names.append(scenario.name)
        #except:
        #    pass
    return analysis.compare_series(datasets, names)

def __get_deficit_stats_comparison(project, analysis_f, units):
    """
    The  the deficit stats comparison dataset for a project.

    Parameters
    ==========
    analysis_f : f(data, gap_attribute_name, target_attribute_name)
        The function that returns the monthly stats dataset for a scenario
    """
    datasets = []
    names = []
    for scenario in project.scenarios.all():
        data = scenario.get_data()
        attribute_name = scenario.get_gap_attribute_name()
        target_name = scenario.get_target_attribute_name()
        monthly_values = analysis_f(data, attribute_name, target_name)
        monthly_values.index.name = "Month"
        monthly_values.name = attribute_name
        datasets.append(monthly_values)
        names.append(scenario.name + " (%s)" % units)
    return analysis.compare_series(datasets, names)

def project_data(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    result = __get_deficit_days_comparison(
        project,
        lambda d, g, t: analysis.monthly_deficit_pct(d, g),
        "Month")
    response = HttpResponse(content_type="application/json")
    result.to_json(response, orient='index')
    return response

#
# Deficit days percent methods. Refactor to API.
#

def project_deficit_days_csv(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    monthly_result = __get_deficit_days_comparison(project,
        lambda d, g, t: analysis.monthly_deficit_pct(d, g),
        "Month")
    annual_result = __get_deficit_days_comparison(project,
        lambda d, g, t: analysis.annual_deficit_pct(d, g), "Annual Average").mean()
    annual_result.name = "Annual Average"
    result = pd.concat([monthly_result, annual_result.to_frame().transpose()], axis=0)
    result.index.name = "Month"
    response = HttpResponse(content_type="text/csv")
    result.to_csv(response)
    return response

def project_deficit_days_annual_csv(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    result = __get_deficit_days_comparison(project,
        lambda d, g, t: analysis.annual_deficit_pct(d, g), "Annual Average").mean()
    response = HttpResponse(content_type="text/csv")
    result.to_csv(response, index_label="Scenario", header=['Annual Average'])
    return response

def project_deficit_days_plot(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    data = __get_deficit_days_comparison(
        project,
        lambda d, g, t: analysis.monthly_deficit_pct(d, g),
        "Month"
    )
    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = new_figure()
    data.plot(kind='bar', ax=ax, table=False)
    ax.set_title("Deficit days comparison")
    ax.yaxis.set_major_formatter(FuncFormatter(to_percent))
    ax.set_ylim([0.0, 1.0])
    return plot_to_response(fig)

#
# Deficit stats volume/percent methods. Refactor to API.
#

def __dataframe_csv_helper(request, project_id, analysis_f, units):
    project = get_object_or_404(Project, pk=project_id)
    result = __get_deficit_stats_comparison(project, analysis_f, units)
    response = HttpResponse(content_type="text/csv")
    result.to_csv(response)
    return response

def __dataframe_annual_csv_helper(request, project_id, analysis_f, units):
    project = get_object_or_404(Project, pk=project_id)
    # This line is the only difference from the above function. There has to
    # be a better way of unifying these!
    result = __get_deficit_stats_comparison(project, analysis_f, units).mean().abs()
    response = HttpResponse(content_type="text/csv")
    # Take the transpose of the series to get a row vector instead of a column
    # vector.
    transpose = result.to_frame().transpose()
    transpose.to_csv(response, index=False)
    return response

def __dataframe_barplot_helper(request, project_id, title, analysis_f,
    units=None, formatter=None, xlim=None, ylim=None):
    project = get_object_or_404(Project, pk=project_id)
    data = __get_deficit_stats_comparison(project, analysis_f, units)
    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = new_figure()
    data.plot(kind='bar', ax=ax, table=False)
    ax.set_title(title)
    if formatter:
        ax.yaxis.set_major_formatter(formatter)
    ylabel = "Volume"
    ax.set_ylabel("Volume (%s)" % units)

    if xlim:
        ax.set_xlim(xlim)
    if ylim:
        ax.set_ylim(ylim)

    return plot_to_response(fig)

def project_deficit_stats_pct_csv(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    monthly_result = __get_deficit_stats_comparison(
        project,
        lambda d, g, t: analysis.monthly_volume_deficit_pct(d, g, t, CFS_TO_AFD).mean().abs(),
        "%")
    annual_result = __get_deficit_stats_comparison(
        project,
        lambda d, g, t: analysis.annual_volume_deficit_pct(d, g, t, CFS_TO_AFD),
        "%").mean().abs()
    annual_result.name = "Annual Average"
    response = HttpResponse(content_type="text/csv")
    result = pd.concat([monthly_result, annual_result.to_frame().transpose()], axis=0)
    result.to_csv(response)
    return response

def project_deficit_stats_annual_pct_csv(request, project_id):
    """
    Stream a CSV with the annual volume deficit stats.
    """
    return __dataframe_annual_csv_helper(request, project_id,
        lambda d, g, t: analysis.annual_volume_deficit_pct(d, g, t, CFS_TO_AFD), "%")

def project_deficit_stats_csv(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    monthly_result = __get_deficit_stats_comparison(
        project,
        lambda d, g, t: analysis.monthly_volume_deficit(d, g, CFS_TO_AFD).mean().abs(),
        "af")
    annual_result = __get_deficit_stats_comparison(
        project,
        lambda d, g, t: analysis.annual_volume_deficit(d, g, CFS_TO_AFD),
        "af").mean().abs()
    annual_result.name = "Annual Average"
    response = HttpResponse(content_type="text/csv")
    result = pd.concat([monthly_result, annual_result.to_frame().transpose()], axis=0)
    result.to_csv(response)
    return response

def project_deficit_stats_annual_csv(request, project_id):
    return __dataframe_annual_csv_helper(request, project_id,
        lambda d, g, t: analysis.annual_volume_deficit(d, g, CFS_TO_AFD), "af")

def project_deficit_stats_plot(request, project_id):
    return __dataframe_barplot_helper(request, project_id, "Average monthly volume deficit",
        lambda d, g, t: analysis.monthly_volume_deficit(d, g, CFS_TO_AFD).mean().abs(),
        "af")

def project_deficit_stats_pct_plot(request, project_id):
    return __dataframe_barplot_helper(request, project_id,
        "Average monthly volume deficit relative to target",
        lambda d, g, t: analysis.monthly_volume_deficit_pct(d, g, t, CFS_TO_AFD).mean().abs(),
        "%", formatter=FuncFormatter(to_percent), ylim=[0.0, 1.0])

def get_low_flows(project_id):
    project = get_object_or_404(Project, pk=project_id)
    names = []
    values = []
    for scenario in project.scenarios.all():
        try:
            data = scenario.get_data()
            value = analysis.low_flow_trend_cfs_per_year(data[scenario.get_attribute_name()], 7, True)
            values.append(value)
            names.append(scenario.name)
        except:
            pass
    frame = pd.Series(values, index=names)
    frame.name = "Trend (cfs/year)"
    frame.index.name = "Scenario"

    return frame

def project_low_flow_csv(request, project_id):
    frame = get_low_flows(project_id)
    response = HttpResponse(content_type='text/csv')
    frame.to_csv(response, index=True, header=True)
    return response

def project_low_flow_plot(request, project_id):
    low_flows = get_low_flows(project_id)
    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = new_figure()
    low_flows.plot(kind='bar', fig=fig, ax=ax)
    #ax.yaxis.set_major_formatter(FuncFormatter(to_percent))
    ax.set_title("7-day Minimum Flow Trend")
    labels = ax.get_xticklabels()
    for label in labels:
        label.set_rotation(0)
    return plot_to_response(fig)

#
# API views
#

class ListProjectScenarioRelationship(generics.ListCreateAPIView):
    queryset = ProjectScenarioRelationship.objects.all()
    serializer_class = ProjectScenarioRelationshipSerializer

class ProjectScenarioRelationshipDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProjectScenarioRelationship.objects.all()
    serializer_class = ProjectScenarioRelationshipSerializer

class ListProjectCropMixRelationship(generics.ListCreateAPIView):
    queryset = ProjectCropMixRelationship.objects.all()
    serializer_class = ProjectCropMixRelationshipSerializer

class ProjectCropMixRelationshipDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProjectCropMixRelationship.objects.all()
    serializer_class = ProjectCropMixRelationshipSerializer
