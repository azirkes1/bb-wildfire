import ee
import streamlit as st
from google.oauth2 import service_account
import geemap
from ee import oauth
import json
import folium 
from folium.plugins import Draw
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import io
from rasterio import MemoryFile
from rasterio.transform import from_origin
from PIL import Image
from collections.abc import Iterable
import zipfile
############################## authorize GEE ##########################################
json_data = st.secrets["json_data"]
service_account = st.secrets["service_account"]

# Preparing values
json_object = json.loads(json_data, strict=False)
service_account = json_object['client_email']
json_object = json.dumps(json_object)

# Authorising the app
credentials = ee.ServiceAccountCredentials(service_account, key_data=json_object)
ee.Initialize(credentials)

#################################### streamlit app layout ###################################################
st.markdown("""
    <style>
        /* Shrink bottom padding */
        .main > div {
            padding-bottom: 0rem;
        }

        /* Hide Streamlit footer and header */
        footer, header, .stDeployButton {
            visibility: hidden;
        }

        /* Optional: reduce block container padding */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
        }

        /* Set a max height for the full app body */
        .main {
            max-height: 90vh;
            overflow-y: auto;
        }

        /* Limit the height of folium map container */
        .folium-map {
            max-height: 500px;
            height: 500px !important;
        }
    </style>
""", unsafe_allow_html=True)

st.title('Bristol Bay')


with st.container():
    #multiselect box 
    options = 'Flamability Hazard', 'Fire Return Interval', 'Land Cover', 'Ownership'
    with st.sidebar:
        selected_options = st.multiselect("Which data layers would you like to download?", options)

    # write the selected options
    st.write("You selected", len(selected_options), 'Data Layers')

    #explain how to select on the map 
    st.write('Please select on the map the area you are interested in.')

    #set up the map
   
    st.session_state.Map = folium.Map(location=[59, -157], zoom_start=8)
    Draw(export=True).add_to(st.session_state.Map)

    #feature collection styling
    def style_featurecollection(fc, color='#000000', width=0.5):
        return fc.map(lambda f: f.set('style', {'color': color, 'width': width}))\
                .style(**{'styleProperty': 'style'})

    #native allotment layer styling
    fc= ee.FeatureCollection('projects/ee-azirkes1/assets/AK_proj/native_allotments')
    styled_fc = style_featurecollection(fc) 

    #add native allotmet layer to map
    folium.TileLayer(
        tiles=styled_fc.getMapId()['tile_fetcher'].url_format,
        attr='Map Data &copy; Google Earth Engine',
        name='Styled FC',
        overlay=True,
        control=True, 
        crs = 'EPSG:3338'
    ).add_to(st.session_state.Map)

    #push map to streamlit
    rendered_map = st_folium(st.session_state.Map, height = 500, width = 1000)

    ######################### bring in data layers ###########################################
    #land ownership
    owner = ee.Image('projects/ee-azirkes1/assets/AK_proj/owner_raster')

    #merge rivers and roads
    water = ee.Image('projects/ee-azirkes1/assets/AK_proj/water_raster')

    #LANDFIRE landcover
    landcover = ee.Image('projects/ee-azirkes1/assets/AK_proj/landcover')

    #LANDFIRE fire return interval
    fri = ee.Image('projects/ee-azirkes1/assets/AK_proj/FRI2')

    #hazard veg
    haz = ee.Image('projects/ee-azirkes1/assets/AK_proj/haz_veg')

    ################################## clip data layers ########################################
    #access draw data
    if rendered_map["last_active_drawing"] is not None:
        last_drawing = rendered_map["last_active_drawing"]
        # Access geometry data
        geometry = last_drawing["geometry"]
        # Access coordinates
        coordinates = geometry["coordinates"]
        polygon = ee.Geometry.Polygon(coordinates)
        feature = ee.Feature(polygon)

        if 'Ownership' in selected_options:

            #select layer and clip it to the user boundary 
            owner_select = owner.select('b1')
            owner_clip = owner_select.clip(polygon)

            #set colors 
            color_map = {
            1: (141, 211, 199), #Air Force
            2: (255, 255, 179), #Alaska Native Allotment
            3: (190, 186, 218), #Alaska Native Lands Patented or Interim Conveyed
            4: (251, 128, 114), #Army
            5: (128, 177, 211), #Bureau of Land Management
            6: (253, 180, 98), #Federal Aviation Administration
            7: (179, 222, 105), #Fish and Wildlife Service
            8: (252, 205, 229), #Local Government
            9: (255, 237, 111), #National Park Service
            10: (188, 128, 189), #Private
            11: (204, 235, 197), #State 
            12: (178, 178, 178) #Undetermined
            }

            #create numpy array from gee image
            array = geemap.ee_to_numpy(owner_clip, region = geometry)

            #Squeeze the last dimension 
            if array.shape[-1] == 1:
                array = array[:, :, 0]  # Now shape is (height, width)

            #create new numpy array with correct shape and convert original categories into colors
            rgb_img = np.zeros((*array.shape, 3), dtype = np.uint8)

            #rgb_img = rgb_img[:, :, 0, :]

            for category, color in color_map.items():
                mask = (array == category)
                rgb_img[mask] = color

            #convert color numpy into jpeg image
            img =Image.fromarray(rgb_img, mode = 'RGB')

            img_bytes_io = io.BytesIO()

            img.save(img_bytes_io, format='JPEG') 
        
            owner_image = img_bytes_io.getvalue()

         

        if 'Land Cover' in selected_options: 
            
            #select layer and clip it to the user boundary 
            lc_select = landcover.select('b1')
            lc_clip = lc_select.clip(polygon)

            #set colors 
            color_map = {
            11: (0, 0, 255), #Water
            12: (159, 161, 240), #Snow/Ice
            21: (253, 204, 211), #Developed - Open Space
            range(21, 25): (255, 122, 143), #Developed
            25: (1, 1, 1),       #Roads
            31: (191, 191, 191), #Barren
            32: (230, 232, 250), #Quarries, Strip Mines, Gravel Pits, Wells, and Wind Pads
            100: (122, 127, 117), #Sparse Vegetation Canopy 
            range(100, 126): (204, 255, 153), #Tree Cover = 10% - 25%
            range(126, 151): (154, 217, 108), #Tree Cover = 26% - 50%
            range(151, 186): (84, 161, 53), #Tree Cover = 51% - 85%
            range(210, 226): (243, 213, 181), #Shrub Cover = 10% - 25%
            range(226, 251): (204, 147, 104), #Shrub Cover = 26% - 50%
            range(251, 265): (191, 102, 75), #Shrub Cover = 51% - 65%
            range(310, 325): (255, 221, 0), #Herb Cover = 10% - 25%
            range(326, 350): (255, 185, 87), #Herb Cover = 26% - 50%
            range(351, 375): (255, 146, 56), #Shrub Cover = 51% - 75%
            }

          # translate range keys
            expanded_color_map = {}
            for key, value in color_map.items():
                if isinstance(key, range):
                    for k in key:
                        expanded_color_map[k] = value
                else:
                    expanded_color_map[key] = value

            #Get array from gee
            array = geemap.ee_to_numpy(lc_clip, region=geometry)  # shape: (height, width, 1)

            #Squeeze the last dimension 
            if array.shape[-1] == 1:
                array = array[:, :, 0]  # Now shape is (height, width)

            #Create RGB image
            rgb_img = np.zeros((*array.shape, 3), dtype=np.uint8)  # shape: (height, width, 3)

            #Apply colors using masks
            for category, color in expanded_color_map.items():
                mask = (array == category)
                rgb_img[mask] = color

            #convert color numpy into jpeg image
            img =Image.fromarray(rgb_img, mode = 'RGB')

            img_bytes_io = io.BytesIO()
            img.save(img_bytes_io, format='JPEG') 
            lc_image = img_bytes_io.getvalue()

            
        if 'Fire Return Interval' in selected_options: 
            #select layer and clip it to the user boundary 
            fri_select = fri.select('b1')
            fri_clip = fri_select.clip(polygon)

            #set colors 
            color_map = {
            (16350, 16370, 16380, 16390, 16400, 16430, 16441, 16443, 16450, 16470, 16510, 16520, 16550, 16560, 16610, 16630, 16650, 16680, 16810, 16850, 16870, 16880, 16970, 16990, 17020, 1760, 17090, 17130, 17140, 17200, 17220): (255, 255, 255), #-9999
            (11, 12, 31, 4428, 4432, 4434, 4455, 4458, 4963, 4965, 7669, 7733, 7737, 16200):(255, 255, 255), #-9999
            (16041, 16120, 16210, 16230): (252, 141, 89), #100 - 149 years
            (16030, 16050, 16281, 16011, 16042, 16061,16101): (254, 224, 139), #150 - 199 years
            (16013, 16822, 16150, 16012, 16141): (255, 255, 191),#200 - 299 years
            (16160, 16180, 16102, 16330, 16240): (217, 239, 139), #300 - 499 years
            (16790, 16142,16091, 16110, 16090): (145, 207, 96), #500 - 999 years
            (16902, 16292, 16282): (26, 152, 80), #1000+ years
            }

            # translate range keys
            expanded_color_map = {}
            for key, value in color_map.items():
                if isinstance(key, range):
                    for k in key:
                        expanded_color_map[k] = value
                else:
                    expanded_color_map[key] = value

            #Get array from gee
            array = geemap.ee_to_numpy(fri_clip, region=geometry)  # shape: (height, width, 1)

            #Squeeze the last dimension 
            if array.shape[-1] == 1:
                array = array[:, :, 0]  # Now shape is (height, width)

            #Create RGB image
            rgb_img = np.zeros((*array.shape, 3), dtype=np.uint8)  # shape: (height, width, 3)

            #Apply colors using masks
            for category, color in expanded_color_map.items():
                # If category is a tuple of values, use np.isin
                if isinstance(category, (list, tuple, np.ndarray)):
                    mask = np.isin(array, category)
                else:
                    mask = (array == category)

                rgb_img[mask] = color

            #convert color numpy into jpeg image
            img =Image.fromarray(rgb_img, mode = 'RGB')

            img_bytes_io = io.BytesIO()
            img.save(img_bytes_io, format='JPEG') 
            fri_image = img_bytes_io.getvalue()

            
        if 'Flamability Hazard' in selected_options: 

            #select layer and clip it to the user boundary 
            haz_select = haz.select('b1')
            haz_clip = haz_select.clip(polygon)

             #set colors 
            color_map = {
            range(0, 10): (101, 171, 20), #0-9
            range(10, 26): (196, 227, 29), #10-25
            range(26, 50): (249, 223, 26), #26-49
            range(50, 75): (255, 154, 11), #50 - 74
            range(75, 100): (252, 59, 9), #75-100
            }

             # translate range keys
            expanded_color_map = {}
            for key, value in color_map.items():
                if isinstance(key, range):
                    for k in key:
                        expanded_color_map[k] = value
                else:
                    expanded_color_map[key] = value

            #Get array from gee
            array = geemap.ee_to_numpy(haz_clip, region=geometry)  # shape: (height, width, 1)

            #Squeeze the last dimension 
            if array.shape[-1] == 1:
                array = array[:, :, 0]  # Now shape is (height, width)

            #Create RGB image
            rgb_img = np.zeros((*array.shape, 3), dtype=np.uint8)  # shape: (height, width, 3)

            #Apply colors using masks
            for category, color in expanded_color_map.items():
                mask = (array == category)
                rgb_img[mask] = color

            #convert color numpy into jpeg image
            img =Image.fromarray(rgb_img, mode = 'RGB')

            img_bytes_io = io.BytesIO()
            img.save(img_bytes_io, format='JPEG') 
            haz_image = img_bytes_io.getvalue()
   


        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            if 'owner_image' in locals():
                zip_file.writestr("ownership.jpg", owner_image)
            if 'lc_image' in locals():
                zip_file.writestr("landcover.jpg", lc_image)
            if 'fri_image' in locals():
                zip_file.writestr("fire_return_interval.jpg", fri_image)
            if 'haz_image' in locals():
                zip_file.writestr("hazard.jpg", haz_image)

        # Move cursor to start of buffer
        zip_buffer.seek(0)

        # Add Streamlit download button
        st.download_button(
                label="Download All Maps as ZIP",
            data=zip_buffer,
            file_name="BB_maps.zip",
            mime="application/zip")
    else:
        st.info("Please draw an area on the map.")






