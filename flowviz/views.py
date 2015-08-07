from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse
from django.core.urlresolvers import reverse

from models import GradedFlowTarget, GradedFlowTargetElement, Scenario

from forms import ScenarioForm, GageDataSourceForm, ExcelDataSourceForm

from waterkit import rasterflow
from waterkit import plotting

from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from pylab import figure
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import matplotlib.colors

import pandas as pd

def index(request):
    scenarios = Scenario.objects.all().order_by('watershed', 'name')
    return render(request, 'flowviz/index.django.html', {'scenarios': scenarios})

def eflow(request):
    scenarios = Scenario.objects.all().order_by('watershed', 'name')
    return render(request, 'flowviz/eflow.django.html',{
        'scenarios': scenarios,
    })

def scenario(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    context = {
        'scenario': scenario,
        'gage_type': Scenario.SOURCE_GAGE,
        'xslx_type': Scenario.SOURCE_EXCEL,
    }
    return render(request, 'flowviz/scenario.django.html', context)

def validate_forms(scenario_form, gage_form, excel_form):
    is_valid = scenario_form.is_valid()
    if scenario_form['source_type'] == Scenario.SOURCE_GAGE:
        is_valid = is_valid and gage_form.is_valid()
    else:
        is_valid = is_valid and excel_form.is_valid()
    return is_valid

def edit_scenario(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    if request.method == 'POST':
        scenario_form = ScenarioForm(request.POST, instance=scenario)
        gage_form = GageDataSourceForm(request.POST, instance=scenario.gage_data)
        excel_form = ExcelDataSourceForm(request.POST, instance=scenario.excel_data)
        if validate_forms(scenario_form, gage_form, excel_form):
            scenario = scenario_form.save()
            if scenario.source_type == Scenario.SOURCE_GAGE:
                gage_form.save()
            elif scenario.source_type == Scenario.SOURCE_EXCEL:
                excel_form.save()
            return redirect(reverse('scenario', args=(scenario.id,)))

    else:
        scenario_form = ScenarioForm(instance=scenario)
        gage_form = GageDataSourceForm(instance = scenario.gage_data)
        excel_form = ExcelDataSourceForm(instance = scenario.excel_data)

    context = {
        'scenario': scenario,
        'scenario_form': scenario_form,
        'gage_form': gage_form,
        'excel_form': excel_form
    }
    return render(request, 'flowviz/scenario_edit.django.html', context)

def dynamic_raster(request, scenario_id, attribute):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()

    # Get visualization parameters
    cmap = request.GET.get('cmap', None)
    title = request.GET.get('title', None)
    zero = request.GET.get('zero', 'False')
    logscale = request.GET.get('logscale', 'False')

    zero = zero == "True"
    logscale = logscale == "True"

    plt.style.use('ggplot')
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
            colormap = rasterflow.create_colormap(data, attribute, colormap, vmin=min_value, vmax=max_value)
        colormap.set_bad('black')
    else:
        colormap = None
    if logscale:
        if min_value <= 0:
            min_value = 0.001
        norm = matplotlib.colors.LogNorm(vmin=min_value, vmax=max_value)
    else:
        norm = None

    rasterflow.raster_plot(data, attribute, title, show_colorbar=True, norm=norm,
                           colormap=colormap, vmin=min_value, vmax=max_value, fig=fig, ax=ax)
    return __plot_to_response(fig)

def __new_figure():
    fig = Figure()
    ax = fig.add_subplot(111)
    return (fig, ax)

def __plot_to_response(fig):
    canvas = FigureCanvas(fig)
    response = HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response

def deficit_stats_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()
    plt.style.use('ggplot')
    fig, ax = __new_figure()
    title = "Volume gap (af/day)"
    plotting.deficit_stats_plot(data, title, fig, ax)
    return __plot_to_response(fig)

def deficit_days_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()
    plt.style.use('ggplot')
    fig, ax = __new_figure()
    title = "Percent of days in deficit"
    ax = plotting.deficit_days_plot(data, title, fig, ax)
    return __plot_to_response(fig)

def right_plot(request, scenario_id):
    scenario = get_object_or_404(Scenario, pk=scenario_id)
    data = scenario.get_data()

    averages = data.groupby('dayofyear').mean()
    plt.style.use('ggplot')
    fig, ax = __new_figure()
    plotdata = averages[['flow', 'e-flow-target']]
    plotdata.columns = ['Average Daily Flow (cfs)', 'Flow Target (cfs)']
    plotdata.plot(ax=ax)
    ax.set_xlabel("Month")
    rasterflow.label_months(ax)
    return __plot_to_response(fig)
