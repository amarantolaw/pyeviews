"""pyeviews: Use EViews directly from python."""
import fnmatch
import gc
import re
import warnings
from pkg_resources import get_distribution
from comtypes.client import CreateObject
import numpy as np
import pandas as pa

#_dist = get_distribution('pyeviews')
#__version__ = _dist.version

# default app if users don't want to specify their own
globalevapp = None

def _BuildFromPython(objlen, newwf=True):
    """Construct EViews command for undated wf"""
    result = "create "  if newwf else "pagecreate "
    result = result + "u " + str(objlen)
    return result

def _BuildFromPandas(obj, newwf=True):
    """Construct EViews command for dated wf"""
    elem_cnt = len(obj)
    # parse the frequency string
    freq_str_all = obj.freqstr
    # check frequency string for custom spacing
    spacing = None
    search_obj = re.search(r'(\d*)(.*)', freq_str_all)
    if search_obj:
        spacing = search_obj.group(1)
        freq_str_all = search_obj.group(2)
    pos = freq_str_all.find("-")
    freq_str = freq_str_all
    freq_str_sp = ' '
    if pos > 0:
        freq_str = freq_str_all[:pos]
        freq_str_sp = '(' + freq_str_all[pos+1:] + ') '
    # - if necessary, convert index to be start of period since 
    # EViews uses the beginning of the period and 
    # we'll have misaligned dates in EViews otherwise
    # - need to separate business freqs from regular otherwise get 
    # misaligned subtractions/additions of dates
    # - note that the DateOffset calculations (sometimes?) give performance warnings
    # fix with resample?
    if freq_str == 'A':
        dtr = obj + pa.DateOffset(years=-1, days=1)
        return _BuildFromPandas(dtr, newwf)
    elif freq_str == 'BA':
        dtr = obj - pa.tseries.offsets.BYearEnd() + pa.tseries.offsets.BDay()
        return _BuildFromPandas(dtr, newwf)
    elif freq_str == 'Q':
        dtr = obj - pa.tseries.offsets.QuarterEnd() + pa.DateOffset(days=1)
        return _BuildFromPandas(dtr, newwf)
    elif freq_str == 'BQ':
        dtr = obj - pa.tseries.offsets.BQuarterEnd() + pa.tseries.offsets.BDay()
        return _BuildFromPandas(dtr, newwf)
    elif freq_str == 'M':
        dtr = obj - pa.tseries.offsets.MonthEnd() + pa.DateOffset(days=1)
        return _BuildFromPandas(dtr, newwf)
    elif freq_str == 'BM':
        dtr = obj - pa.tseries.offsets.BMonthEnd() + pa.tseries.offsets.BDay()
        return _BuildFromPandas(dtr, newwf)
    # first part of the EViews command
    result = "create " if newwf else "pagecreate "
    # construct the time period strings
    yr_begin = str(obj[0].year)
    yr_end = str(obj[elem_cnt - 1].year)
    mo_begin = str(obj[0].month)
    mo_end = str(obj[elem_cnt - 1].month)
    day_begin = str(obj[0].day)
    day_end = str(obj[elem_cnt - 1].day)
    date_begin = mo_begin + '/' + day_begin + '/' + yr_begin + ' '
    date_end = mo_end + '/' + day_end + '/' + yr_end + ' '
    dow_begin = str(obj[0].dayofweek + 1) # EV d.o.w. has Mon = 1
    dow_end = str(obj[elem_cnt - 1].dayofweek + 1)
    time_begin = str(obj[0].strftime('%H')) + ':' + \
                 str(obj[0].strftime('%M')) + ':' + \
                 str(obj[0].strftime('%S')) + ' '
    time_end = str(obj[elem_cnt - 1].strftime('%H')) + ':' + \
               str(obj[elem_cnt - 1].strftime('%M')) + ':' + \
               str(obj[elem_cnt - 1].strftime('%S')) + ' '
    time_min = str(obj.hour.min().item()) + ':' + \
               str(obj.minute.min().item()) + ':' + \
               str(obj.second.min().item()) 
    time_max = str(obj.hour.max().item()) + ':' + \
               str(obj.minute.max().item()) + ':' + \
               str(obj.second.max().item())    
    # yearly
    if (freq_str in ['AS', 'A', 'BAS', 'BA'] and \
        spacing in ['2', '3', '4', '5', '6', '7', '8', '9', '10', '20']):
            # month alignment not allowed for multi-year freqs in EViews
            result = result + spacing + 'a ' + date_begin + date_end
    elif (freq_str in ['AS', 'A', 'BAS', 'BA'] and not spacing):
        result = result + 'a' + freq_str_sp + date_begin + date_end
    # quarterly
    elif (freq_str in ['QS', 'Q', 'BQS', 'BQ'] and not spacing):
        result = result + 'q' + freq_str_sp + date_begin + date_end
    # monthly
    elif (freq_str in ['MS', 'M', 'BMS', 'BM', 'CBMS', 'CBM'] and not spacing): 
        result = result + 'm' + freq_str_sp  + date_begin + date_end
    # weekly
    elif (freq_str == 'W' and not spacing): 
        result = result + 'w' + freq_str_sp + date_begin + date_end
    # daily
    elif (freq_str == 'D' and not spacing):
        result = result + 'd7' + freq_str_sp + date_begin + date_end
    # daily (business days)
    elif (freq_str == 'B' and not spacing):
        result = result + 'd5' + freq_str_sp + date_begin + date_end
    # daily (custom days)
    elif (freq_str == 'C' and not spacing):
        result = result + 'd(' + dow_begin + ',' + dow_end + ') ' + \
                 freq_str_sp + date_begin + date_end    
    # hourly
    elif (freq_str in ['H', 'BH'] and (not spacing or \
        spacing in ['2', '4', '6', '8', '12'])):
            result = result + spacing + 'h(' + dow_begin + '-' + dow_end + \
                     ', ' + time_min + ' - ' + time_max + ') ' + \
                     date_begin + time_begin + date_end + time_end
            if spacing:
            warnings.warn("Hourly pandas DatetimeIndex may not be exactly \
                              replicated in EViews.  See EViews documentation \
                              for details.")
    # minutes
    elif (freq_str in ['T', 'min'] and (not spacing or \
        spacing in ['2', '5', '10', '15', '20', '30'])):
            result = result + spacing + 'Min(' + dow_begin + '-' + dow_end + \
                    ', ' + time_min + ' - ' + time_max + ') ' + \
                     date_begin + time_begin + date_end + time_end
    # seconds
    elif (freq_str == 'S' and (not spacing or spacing in ['5', '15', '30'])):
            result = result + spacing + 'Sec(' + dow_begin + '-' + dow_end + \
                    ', ' + time_min + ' - ' + time_max + ') ' + \
                     date_begin + time_begin + date_end + time_end
    # EViews doesn't support these frequencies
    elif (freq_str in ['L', 'ms', 'U', 'us', 'N']):
        raise ValueError('Frequency ' + freq_str
                         + ' is not supported in EViews.')
    else:
        raise ValueError('Frequency ' + spacing
                         + freq_str + ' is not supported in EViews.')
    return result   
    
def _CheckReservedNames(names):
    """Check for disallowed names in EViews."""
    if 'c' in names:
        raise ValueError('c is not an allowed name for a series.')
    if 'resid' in names:
        raise ValueError('resid is not an allowed name for a series.')

def _GetApp(app=None):
    """Return app (user-defined or default)"""
    global globalevapp
    if app is not None:
        return app
    if globalevapp is None:
        globalevapp = GetEViewsApp(instance='new')
    return globalevapp
    
def Cleanup():
    """Clean up"""
    global globalevapp
    if globalevapp is not None:
        globalevapp = None
    gc.collect()

def PutPythonAsWF(obj, app=None, newwf=True):
    """Push Python data to EViews."""
    app = _GetApp(app)
    # which python data structure is obj?
    if isinstance(obj, pa.core.frame.DataFrame):
        #create a new EViews workfile with the right frequency
        create = _BuildFromPandas(obj.index, newwf)
        app.Run(create)
        _CheckReservedNames(obj.columns)
        # loop through all columns, push each into EViews as a list
        for col in obj.columns:
            col_data = obj[col].tolist()
            app.PutSeries(col, col_data)
    elif isinstance(obj, pa.core.series.Series):
        #create a new EViews workfile with the right frequency
        create = _BuildFromPandas(obj.index, newwf)
        app.Run(create)
        # push the data into EViews as a list
        name = "series"
        if obj.name:
            name = obj.name
            _CheckReservedNames([name])
        data = obj.tolist()
        app.PutSeries(name, data)
    elif isinstance(obj, pa.core.indexes.datetimes.DatetimeIndex):
        #create a new EViews workfile with the right frequency
        create = _BuildFromPandas(obj, newwf)
        app.Run(create)
    elif isinstance(obj, pa.core.panel.Panel):
        #create a new EViews workfile with the right frequency
        create = _BuildFromPandas(obj.major_axis, newwf)
        create = create + str(len(obj.items))
        app.Run(create)
        # concatenate items into single dataframe
        # loop through and push each column into EViews as a list
        result = pa.concat([obj[item] for item in obj.items])
        _CheckReservedNames(result.columns)
        for col in result.columns:
            #col_name = obj.columns[col_index]
            #col_data = list(obj.values[col_index])
            col_data = result[col].tolist()
            app.PutSeries(col, col_data)  
    elif isinstance(obj, list):
        # create a new undated workfile with the right length
        length = len(obj)
        create = _BuildFromPython(length, newwf)
        app.Run(create)
        # push the data into EViews as a list
        app.PutSeries("series", obj)
    elif isinstance(obj, dict):
        # create a new undated workfile with the right length
        length = max(len(item) for item in obj.values())
        create = _BuildFromPython(length, newwf)
        app.Run(create)
        _CheckReservedNames(obj.keys())
        # loop through the dict and push the data into EViews as a list
        for key in obj:
            data = obj[key]
            app.PutSeries(str(key), data)
    elif isinstance(obj, np.ndarray):
        # create a new undated workfile with the right length
        create = _BuildFromPython(obj.shape[0], newwf)
        app.Run(create)
        # loop through the array, push the data into EViews as a list
        # note that nested arrays may not be transferred properly
        # is it a structured array?
        if obj.dtype.names:
            for name in obj.dtype.names:
                data = obj[name].tolist()
                app.PutSeries(name, data)
        else:
            for col_num in range(obj.shape[1]):
            name = "series" + str(col_num)
                data = obj[:, col_num].tolist()
            app.PutSeries(name, data)        
    else:
        raise ValueError('Unsupported type: ' + str(type(obj)))

def GetWFAsPython(app=None, wfname='', pagename='', namefilter='*'):
    """Move EViews data to Python."""
    app = _GetApp(app)
    # being lazy here and storing duplicate keys for completeness
    dt_map = {'D5':'B', '5':'B', 'D7':'C', 'D7':'D', '7':'D', 'D':'C',
              'W':'W', 'M':'MS', 'Q':'QS', 'A':'AS', 'Y':'AS', 
              'H':'H', 'Min':'T', 'Min':'min', 'Sec':'S'}
    # load the workfile 
    if wfname != '':
        app.Run("wfuse " + wfname) # needs full pathname
    
    if pagename:
        #change workfile page to specified page name
        if app.Get('=@pageexist("' + str(pagename) + '")') == 1:
            app.Run("pageselect " + str(pagename))
        else:
            raise ValueError('Invalid pagename: ' + str(pagename))
    # get workfile frequency
    pgfreq = app.Get("=@pagefreq")
    # reset sample range to all
    app.Run("smpl @all")
    # is the workfile a panel?
    ispanel = app.Get("=@ispanel")
    # get series names as a 1-dim array
    snames = app.Lookup(namefilter, "series", 1)
    if not snames:
        raise ValueError('No series objects found.')
    # build Datetimeindex object
    if pgfreq in ['2Y', '3Y', '4Y', '5Y', '6Y', '7Y', '8Y', '9Y', '10Y', '20Y',
                  'S', 'BM', 'F', 'T', '2H', '4H', '6H', '8H', '12H',
                  '2Min', '5Min', '10Min', '15Min', '20Min', '30Min',
                  '5Sec', '15Sec', '30Sec']:
        raise ValueError(pgfreq + ' is not supported in pandas.')
    elif (pgfreq in ['D5', '5', 'D7', 'D7', '7', 'D',
                    'W', 'M', 'Q', 'A', 'Y', 'H', 'Min', 'Min', 'Sec'] or 
                    fnmatch.fnmatch(pgfreq, 'D(*)')):
        #get index series
        dates = app.GetSeries("@date")
        if fnmatch.fnmatch(pgfreq, 'D(*)'):
            idx = pa.DatetimeIndex(dates, freq='C')
        else:
            idx = pa.DatetimeIndex(dates, freq=dt_map[pgfreq])
    elif pgfreq == 'U':
        pass
    else:
        raise ValueError('Unsupported workfile frequency: ' + pgfreq)
    # get series names as a space delimited string
    snames_str = app.Lookup(namefilter, "series")
    # retrieve all series data as a single call
    grp = app.GetGroup(snames_str, "@all")
    if (pgfreq in ['D5', '5', 'D7', 'D7', '7', 'D', \
                   'W', 'M', 'Q', 'A', 'Y', 'H', 'Min', 'Min', 'Sec'] or \
                   fnmatch.fnmatch(pgfreq, 'D(*)')):
        # for dated workfiles create the dataframe
        # build dataframe with empty columns 
        dfr = pa.DataFrame(index=idx, columns=list(snames))
        #for each series name, extract the data from our grp array
        for sindex in range(len(snames)):
            dfr[snames[sindex]] = [col[sindex] for col in grp]
        data = dfr
    elif pgfreq == 'U':
        # for undated workfiles we don't pass in an index
        dfr = pa.DataFrame(columns=list(snames))
        # for each series name, extract the data from our grp array
        for sindex in range(len(snames)):
            dfr[snames[sindex]] = [col[sindex] for col in grp]
        data = dfr
    if ispanel:
        crossids = dfr['CROSSID'].unique()
        datadict = {elem: pa.DataFrame for elem in crossids}
        for key in datadict.keys():
            datadict[key] = dfr[:][dfr['CROSSID'] == key]
            datadict[key].drop(['CROSSID', 'DATEID'], axis=1, inplace=True)
        data = pa.Panel(datadict)   
    # close the workfile
    #app.Run("wfclose")   
    return data
    
def GetEViewsApp(version='EViews.Manager', instance='either', showwindow=False): 
    """Allow for more control of the app"""
    # get manager object
    # this is an optional function for greater control of the app object
    # otherwise can just use the global app object
    try:
        mgr = CreateObject(version)
    except WindowsError:
        #if mgr is None:
        raise WindowsError(version + " not found.")
    if mgr is None:
        raise WindowsError(version + " not found.")
    # dictionary for type of EViews instance
    # 0 = new EViews, 1 = new or existing, 2 = existing
    table = {'new':0, 'either':1, 'existing':2}
    # get application object
    try:
        app = mgr.GetApplication(table[instance])
    except Exception:
        raise WindowsError("Problem with " + version + " EViews installation.\
                           Verify that EViews runs and is properly licensed.")
    if app is None:
        raise WindowsError("Problem with " + version + " EViews installation.\
                           Verify that EViews runs and is properly licensed.")
    # release manager object
    mgr = None
    # show EViews window
    if showwindow:
        app.Show() #optional
    return app
    
def Run(command, app=None):
    """Send commands to EViews."""
    app = _GetApp(app)
    app.Run(command)   
    
def Get(objname, app=None):
    """Retrieve the results of EViews commands."""
    app = _GetApp(app)
    return app.Get(objname)
