from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, Http404
from django.core import serializers
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.template.defaultfilters import slugify

from rest_pandas import PandasSimpleView

from waterkit.flow import plotting, analysis

from utils.mpl import new_figure, plot_to_response, to_percent

from utils.views import EditObjectView

from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from pylab import figure
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import matplotlib.colors
from matplotlib.ticker import FuncFormatter

from bokeh.resources import CDN
from bokeh.embed import components

from datetime import datetime

import pandas as pd

import json

from models import Scenario, CyclicTargetElement
from forms import ScenarioForm
from forms import CyclicTargetElementFormSet

from datafiles.forms import FileUploadForm
from datafiles.models import DataFile

import plots

from econ.views import read_crop_mix, get_bls_key
import econ.plots

DEFAULT_PLOT_STYLE = 'ggplot'

#
# Scenario methods.
#

class ScenarioView(View):
    template_name = 'flowviz/scenario.django.html'

    def get(self, request, scenario_id):
        scenario = get_object_or_404(Scenario, pk=scenario_id)
        def convert_element(element):
            return CyclicTargetElement(
                target_value = float(element.target_value) * scenario.attribute_multiplier,
                from_month = element.from_month,
                from_day = element.from_day,
                to_month = element.to_month,
                to_day = element.to_day
            )
        if scenario.source_type == Scenario.SOURCE_GAGE:
            converted_targets = map(convert_element,
                scenario.cyclictargetelement_set.all())
        else:
            converted_targets = None

        context = {
            'scenario': scenario,
            'attribute_name': scenario.get_attribute_name(),
            'gap_attribute_name': scenario.get_gap_attribute_name(),
            'converted_targets': converted_targets,
            'gage_type': Scenario.SOURCE_GAGE,
            'xslx_type': Scenario.SOURCE_EXCEL,
            'title': scenario.name,
            'year': datetime.now().year,
            'project_name': request.GET.get('projectname', None),
        }
        return render(request, self.template_name, context)

def scenario_data(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data().to_json()
    return HttpResponse(data, content_type="application/json")

def dynamic_raster(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()

    # Get visualization parameters
    attribute = request.GET.get('attribute', None)
    if not attribute:
        return HttpResponseBadRequest()
    cmap = request.GET.get('cmap', None)
    title = request.GET.get('title', None)
    zero = request.GET.get('zero', 'False')
    logscale = request.GET.get('logscale', 'False')

    zero = zero == "True"
    logscale = logscale == "True"

    plt.style.use(DEFAULT_PLOT_STYLE)
    fig = Figure()
    ax = fig.add_subplot(111)

    if not zero:
        min_value = data[attribute].min()
        max_value = data[attribute].max()
    else:
        min_value = data[attribute].min()
        max_value = abs(data[attribute].min())
    if cmap:
        colormap = cm.get_cmap(cmap)
        if zero:
            colormap = plotting.create_colormap(data, attribute, colormap, vmin=min_value, vmax=max_value)
        colormap.set_bad('black')
    else:
        colormap = None
    if logscale:
        if min_value <= 0:
            min_value = 0.001
        norm = matplotlib.colors.LogNorm(vmin=min_value, vmax=max_value)
    else:
        norm = None

    plotting.rasterplot(data, attribute, title, show_colorbar=True, norm=norm,
                           colormap=colormap, vmin=min_value, vmax=max_value, fig=fig, ax=ax)
    return plot_to_response(fig)

def __label_scenario_attribute(scenario):
    return "Flow (cfs)"

def __label_volume_attribute(scenario):
    return "Volume (af)"

def __setup_scenario_plot(scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    plt.style.use(DEFAULT_PLOT_STYLE)
    return scenario, new_figure()

def deficit_stats_plot(request, scenario_id):
    scenario, (fig, ax) = __setup_scenario_plot(scenario_id)
    ax.set_ylabel(__label_volume_attribute(scenario))
    title = "Monthly Volume Deficit"
    plotting.volume_deficit_monthly(scenario.get_data(), scenario.get_gap_attribute_name(), title, fig, ax)
    return plot_to_response(fig)

def deficit_stats_plot_annual(request, scenario_id):
    scenario, (fig, ax) = __setup_scenario_plot(scenario_id)
    ax.set_ylabel(__label_volume_attribute(scenario))
    title = "Annual Volume Deficit"
    plotting.volume_deficit_annual(scenario.get_data(), scenario.get_gap_attribute_name(), title, fig, ax)
    return plot_to_response(fig)

def deficit_stats_pct_plot(request, scenario_id):
    scenario, (fig, ax) = __setup_scenario_plot(scenario_id)
    ax.yaxis.set_major_formatter(FuncFormatter(to_percent))
    ax.set_ylim([0.0, 1.0])
    plotting.volume_deficit_pct_monthly(
        scenario.get_data(),
        scenario.get_gap_attribute_name(),
        scenario.get_target_attribute_name(),
        "Monthly Volume Deficit Relative to Target",
        fig, ax
    )
    return plot_to_response(fig)

def deficit_stats_pct_plot_annual(request, scenario_id):
    scenario, (fig, ax) = __setup_scenario_plot(scenario_id)
    ax.yaxis.set_major_formatter(FuncFormatter(to_percent))
    ax.set_ylim([0.0, 1.0])
    plotting.volume_deficit_pct_annual(
        scenario.get_data(),
        scenario.get_gap_attribute_name(),
        scenario.get_target_attribute_name(),
        "Annual Volume Deficit Relative to Target",
        fig, ax
    )
    return plot_to_response(fig)

def deficit_days_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()
    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = new_figure()
    title = "Monthly Temporal Deficit"
    ax = plotting.deficit_days_plot(data, scenario.get_gap_attribute_name(), title, fig, ax)
    ax.yaxis.set_major_formatter(FuncFormatter(to_percent))
    ax.set_ylim([0.0, 1.0])
    return plot_to_response(fig)

def annual_deficit_days_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()
    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = new_figure()
    title = "Annual Temporal Deficit"
    ax = plotting.annual_deficit_days_plot(
        data,
        scenario.get_gap_attribute_name(),
        title, fig, ax
    )
    ax.yaxis.set_major_formatter(FuncFormatter(to_percent))
    ax.set_ylim([0.0, 1.0])
    return plot_to_response(fig)

def right_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()

    daygroups = data.groupby(lambda x: x.dayofyear)
    low = daygroups[scenario.get_attribute_name()].quantile(0.2)
    median = daygroups[scenario.get_attribute_name()].quantile(0.5)
    high = daygroups[scenario.get_attribute_name()].quantile(0.8)
    target = daygroups[scenario.get_target_attribute_name()].mean()

    plotdata = pd.concat([low, median, high, target], axis=1)
    plotdata.columns = ["80% Exceedance", "Median", "20% Exceedance", "Target"]

    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = new_figure()
    plotdata.plot(ax=ax)
    ax.set_xlabel("Month")
    ax.set_ylabel(__label_scenario_attribute(scenario))
    plotting.label_months(ax)
    return plot_to_response(fig)

def long_term_minimum_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()

    column = scenario.get_attribute_name()
    min_data = analysis.annual_minimum(data[column], 7, True)
    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = new_figure()
    plotting.plot_with_trendline_ols(
        min_data,
        title="7-day Minimum Flow",
        fig=fig, ax=ax)
    ax.set_xlabel("Year")
    ax.set_ylabel(__label_scenario_attribute(scenario))
    return plot_to_response(fig)

def temporal_deficit_drought_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    quantile = 1.0 - (scenario.drought_exceedance / 100.0)
    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = plots.plot_drought_temporal_deficit_mpl(scenario, quantile)
    ax.yaxis.set_major_formatter(FuncFormatter(to_percent))
    ax.set_xlabel("Year")
    ax.set_ylabel("Percent of days")
    return plot_to_response(fig)

def volume_deficit_drought_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    quantile = 1.0 - (scenario.drought_exceedance / 100.0)
    plt.style.use(DEFAULT_PLOT_STYLE)
    fig, ax = plots.plot_drought_volume_deficit_mpl(scenario, quantile)
    ax.set_xlabel("Year")
    ax.set_ylabel("Volume (af)")
    return plot_to_response(fig)

class AgriculturePlotView(View):
    xlabel = None
    ylabel = None

    def get(self, request, scenario_id):
        scenario = get_object_or_404(Scenario, pk=scenario_id)
        plt.style.use(DEFAULT_PLOT_STYLE)
        # Crop data.
        if scenario.crop_mix:
            crop_mix, data, years, commodities = read_crop_mix(scenario.crop_mix.id)
            groups = [g.as_cropgroup() for g in crop_mix.cropmixgroup_set.all()]
            dataframe = self.data_function(data, groups)
            fig, ax = new_figure()
            self.plot_function(dataframe, ax)
            ax.set_xlabel(self.xlabel)
            ax.set_ylabel(self.ylabel)
            return plot_to_response(fig)
        else:
            raise Http404("Scenario contains no agriculture data.")

    def data_function(self, data, groups):
        raise NotImplementedError

    def plot_function(self, dataframe, ax):
        raise NotImplementedError

class CropAreaView(AgriculturePlotView):
    xlabel = "Year"
    ylabel = "Acres"
    def data_function(self, data, groups):
        return data.get_table("ACRES", groups)
    def plot_function(self, dataframe, ax):
        dataframe.plot.area(ax=ax)

class CropFractionView(AgriculturePlotView):
    xlabel = "Year"
    ylabel = "Percent of Area"
    def data_function(self, data, groups):
        return data.get_ratio_table("ACRES", groups)
    def plot_function(self, dataframe, ax):
        dataframe.plot.bar(stacked=True, ax=ax)
        ax.yaxis.set_major_formatter(FuncFormatter(to_percent))

class CropRevenueView(AgriculturePlotView):
    xlabel = "Year"
    ylabel = "Dollars"

    @staticmethod
    def format_millions_of_dollars(value, position):
        return "$%1.1fM" % (value * 1e-6)

    def data_function(self, data, groups):
        return data.get_derived_table("Revenue", groups)
    def plot_function(self, dataframe, ax):
        dataframe.plot.bar(stacked=True, ax=ax)
        ax.yaxis.set_major_formatter(FuncFormatter(CropRevenueView.format_millions_of_dollars))

class CropNIWRView(AgriculturePlotView):
    xlabel = "Year"
    ylabel = "Acre-Feet"
    def data_function(self, data, groups):
        return data.get_derived_table("NIWR", groups)
    def plot_function(self, dataframe, ax):
        dataframe.plot.bar(stacked=True, ax=ax)

class CropRevenuePerAFView(AgriculturePlotView):
    xlabel = "Year"
    ylabel = "Dollars per Acre-Foot"
    def data_function(self, data, groups):
        revenue_table = data.get_derived_table("Revenue", groups)
        niwr_table = data.get_derived_table("NIWR", groups)
        result_table = revenue_table.sum(axis=1) /  niwr_table.sum(axis=1)
        return result_table
    def plot_function(self, dataframe, ax):
        dataframe.plot.bar(ax=ax)

class CropLaborView(AgriculturePlotView):
    xlabel = "Year"
    ylabel = "FTEs (2080 Hours/Year)"
    def data_function(self, data, groups):
        return data.get_derived_table("Labor", groups).div(2080)
    def plot_function(self, dataframe, ax):
        dataframe.plot.bar(stacked=True, ax=ax)

class EditScenario(EditObjectView):
    template_name = "scenarios/scenario_edit.django.html"
    model = Scenario
    form = ("scenario", ScenarioForm)
    formsets = {
        "target_formset": CyclicTargetElementFormSet
    }
    title = "Edit Scenario"
    url_name = "scenario-edit"
    redirect_url_name = "scenario"
    redirect_parameter_name = "scenario_id"
    additional_context = {
        "upload_form": FileUploadForm(),
    }

class DownloadScenarioData(PandasSimpleView):
    def get_data(self, request, scenario_id):
        scenario = get_object_or_404(Scenario, pk=scenario_id)
        return scenario.get_data()

    def get(self, request, *args, **kwargs):
        scenario = get_object_or_404(Scenario, pk=kwargs["scenario_id"])
        response = super(DownloadScenarioData, self).get(request, *args, **kwargs)
        filename = slugify(scenario.name)
        response["Content-Disposition"] = "attachment;filename={:}.{:}".format(
            filename,
            request.query_params.get("format", "")
        )
        return response
