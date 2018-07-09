import os

import numpy as np
import pandas as pd

from .structures.base import StructuresDict
from .filters import ALL_FILTERS
from .io import FROM, TO
from .neighbors import k_neighbors, r_neighbors
from .plot import DESCRIPTION, plot_PyntCloud
from .samplers import ALL_SAMPLERS
from .scalar_fields import ALL_SF
from .structures import ALL_STRUCTURES
from .utils.dataframe import convert_columns_dtype


class PyntCloud(object):
    """A Pythonic Point Cloud."""

    def __init__(self, points, mesh=None, structures={}, **kwargs):
        """Create PyntCloud.

        Parameters
        ----------
        points: pd.DataFrame
            DataFrame of N rows by M columns.
            Each row represents one point of the point cloud.
            Each column represents one scalar field associated to its corresponding point.

        mesh: pd.DataFrame or None, optional
            Default: None
            Triangular mesh associated with points.

        structures: dict, optional
            Map key(base.Structure.id) to val(base.Structure)

        kwargs: custom attributes
        """
        self.points = points
        self.mesh = mesh
        self.structures = StructuresDict()
        for key, val in structures.items():
            self.structures[key] = val
        for key, val in kwargs.items():
            setattr(self, key, val)
        # store raw xyz values to share memory along structures
        self.xyz = self.points[["x", "y", "z"]].values
        self.centroid = self.xyz.mean(0)

    def __repr__(self):
        default = [
            "_PyntCloud__points",
            "_PyntCloud__mesh",
            "structures",
            "xyz",
            "centroid"
        ]
        others = ["\n\t {}: {}".format(x, str(type(getattr(self, x))))
                  for x in self.__dict__ if x not in default]

        if self.mesh is None:
            n_faces = 0
        else:
            n_faces = len(self.mesh)

        return DESCRIPTION.format(
            len(self.points), len(self.points.columns) - 3,
            n_faces,
            self.structures.n_kdtrees,
            self.structures.n_voxelgrids,
            self.centroid[0], self.centroid[1], self.centroid[2],
            "".join(others))

    @property
    def points(self):
        return self.__points

    @points.setter
    def points(self, df):
        if not isinstance(df, pd.DataFrame):
            raise TypeError("Points argument must be a DataFrame")
        elif not set(['x', 'y', 'z']).issubset(df.columns):
            raise ValueError("Points must have x, y and z coordinates")
        self._update_points(df)

    @property
    def mesh(self):
        return self.__mesh

    @mesh.setter
    def mesh(self, df):
        # allow PyntCloud to don't have mesh assigned
        if df is not None:
            if not isinstance(df, pd.DataFrame):
                raise TypeError("Mesh argument must be a DataFrame")
            elif not set(['v1', 'v2', 'v3']).issubset(df.columns):
                print(df.columns)
                raise ValueError(
                    "Mesh must have v1, v2 and v3 columns, at least")
            self.__mesh = df
        else:
            self.__mesh = None

    @classmethod
    def from_file(cls, filename, **kwargs):
        """Extract data from file and construct a PyntCloud with it.

        Parameters
        ----------
        filename: str
            Path to the file from which the data will be read

        kwargs: only usable in some formats

        Returns
        -------
        PyntCloud: object
            PyntCloud instance, containing all valid elements in the file.
        """
        ext = filename.split(".")[-1].upper()
        if ext not in FROM:
            raise ValueError(
                "Unsupported file format; supported formats are: {}".format(list(FROM)))
        else:
            return cls(**FROM[ext](filename, **kwargs))

    def to_file(self, filename, also_save=None, **kwargs):
        """Save PyntCloud data to file.

        Parameters
        ----------
        filename: str
            Path to the file from which the data will be read

        also_save: list of str, optional
            Default: None
            Names of the attributes that will be extracted from the PyntCloud
            to be saved in addition to points. Usually also_save=["mesh"]

        kwargs: only usable in some formats
        """
        convert_columns_dtype(self.points, np.float64, np.float32)
        ext = filename.split(".")[-1].upper()
        if ext not in TO:
            raise ValueError(
                "Unsupported file format; supported formats are: {}".format(list(TO)))
        kwargs["filename"] = filename
        kwargs["points"] = self.points
        if also_save is not None:
            for x in also_save:
                kwargs[x] = getattr(self, x)

        TO[ext](**kwargs)

    def add_scalar_field(self, name, **kwargs):
        """Add one or multiple columns to PyntCloud.points.

        Parameters
        ----------
        name: str
            One of the available names. See below.
        kwargs
            Vary for each name. See below.

        Returns
        -------
        sf_added: list of str
            The name of each of the columns (scalar fields) added.
            Useful for chaining operations that require string names.

        Notes
        -----

        Available scalar fields are:

        **REQUIRE EIGENVALUES**

            ARGS
                ev: list of str
                    ev = self.add_scalar_field("eigen_values", ...)

            sphericity

            anisotropy

            linearity

            omnivariance

            eigenentropy

            planarity

            eigen_sum

            curvature

        **REQUIRE K_NEIGHBORS**

            ARGS
                k_neighbors: (N, k) ndarray
                    Returned from: self.get_neighbors(k, ...) /
                    manually querying some self.kdtrees[x] /
                    other methods.

            eigen_decomposition

            eigen_values

        **REQUIRE NORMALS**

            orientation_degrees

            orientation_radians

            inclination_radians

            inclination_degrees

        **REQUIRE RGB**

            hsv

            relative_luminance

            rgb_intensity


        **REQUIRE VOXELGRID**

            ARGS
                voxelgrid_id: VoxelGrid.id
                    voxelgrid_id = self.add_structure("voxelgrid", ...)

            voxel_x

            voxel_y

            voxel_n

            voxel_z

            euclidean_clusters


        **ONLY REQUIRE XYZ**

            plane_fit
                max_dist: float, optional
                    Default: 1e-4
                    Maximum distance from point to model in order to be considered as inlier.
                max_iterations: int, optional (Default 100)
                    Maximum number of fitting iterations.

            sphere_fit
                max_dist: float, optional
                    Default: 1e-4
                    Maximum distance from point to model in order to be considered as inlier.
                max_iterations: int, optional
                    Default: 100
                    Maximum number of fitting iterations.

            custom_fit
                model: subclass of ransac.models.RansacModel
                    Model to be fitted
                sampler: subclass of ransac.models.RansacSampler
                    Sample method to be used
                name: str
                    Will be used to name the added column
                model_kwargs: dict, optional
                    Default: {}
                    Will be passed to single_fit function.
                sampler_kwargs: dict, optional
                    Default: {}
                    Will be passed to single_fit function.

            spherical_coords
                degrees: bool, optional
                    Default: True.
                    Return polar and azimuthal angles in degrees.
        """
        if name in ALL_SF:
            scalar_field = ALL_SF[name](pyntcloud=self, **kwargs)
            scalar_field.extract_info()
            scalar_field.compute()
            scalar_fields_added = scalar_field.get_and_set()

        else:
            raise ValueError("Unsupported scalar field. Check docstring")

        return scalar_fields_added

    def add_structure(self, name, **kwargs):
        """Build a structure and add it to the corresponding PyntCloud's attribute.

        Parameters
        ----------
        name: str
            One of the available names. See below.
        kwargs
            Vary for each name. See below.

        Returns
        -------
        structure.id: str
            Identification string associated with the added structure.
            Useful for chaining operations that require string names.

        Notes
        -----
        Available structures are:

        **ONLY REQUIRE XYZ**

            kdtree
                leafsize: int, optional
                    Default: 16
                    The number of points at which the algorithm switches over to brute-force.
                    Has to be positive.

            voxelgrid
                x_y_z: list of int, optional
                    Default: [2, 2, 2]
                    The number of segments in which each axis will be divided.
                    x_y_z[0]: x axis
                    x_y_z[1]: y axis
                    x_y_z[2]: z axis
                    If sizes is not None it will be ignored.
                sizes: list of float, optional
                    Default: None
                    The desired voxel size along each axis.
                    sizes[0]: voxel size along x axis.
                    sizes[1]: voxel size along y axis.
                    sizes[2]: voxel size along z axis.
                bb_cuboid: bool, optional
                    Default: True
                    If True, the bounding box of the point cloud will be adjusted
                    in order to have all the dimensions of equal length.

            octree
                TODO

        """
        if name in ALL_STRUCTURES:
            info = ALL_STRUCTURES[name].extract_info(pyntcloud=self)
            structure = ALL_STRUCTURES[name](**info, **kwargs)
            structure.compute()
            structure_added = structure.get_and_set(self)

        else:
            raise ValueError("Unsupported structure. Check docstring")

        return structure_added

    def get_filter(self, name, and_apply=False, **kwargs):
        """Compute filter over PyntCloud's points and return it.

        Parameters
        ----------
        name: str
            One of the available names. See below.

        and_apply: boolean, optional
            Default: False
            If True, filter will be applied to self.points

        kwargs
            Vary for each name. See below.

        Returns
        -------
        filter: boolean array
            Boolean mask indicating wherever a point should be keeped or not.
            The size of the boolean mask will be the same as the number of points
            in the pyntcloud.

        Notes
        -----

        Available filters are:

        **REQUIRE KDTREE**

            ARGS
                kdtree : KDTree.id
                    kdtree = self.add_structure("kdtree", ...)

            ROR    (Radius Outlier Removal)
                k: int
                    Number of neighbors that will be used to compute the filter.
                r: float
                    The radius of the sphere with center on each point. The filter
                    will look for the required number of neighboors inside that sphere.

            SOR    (Statistical Outlier Removal)
                k: int
                    Number of neighbors that will be used to compute the filter.
                z_max: float
                    The maximum Z score which determines if the point is an outlier.

        **ONLY REQUIRE XYZ**

            BBOX    (Bounding Box)
                min_i, max_i: float
                    The bounding box limits for each coordinate. If some limits are missing,
                    the default values are -infinite for the min_i and infinite for the max_i.

        """
        if name in ALL_FILTERS:
            pointcloud_filter = ALL_FILTERS[name](pyntcloud=self, **kwargs)
            pointcloud_filter.extract_info()
            boolean_array = pointcloud_filter.compute()

            if and_apply:
                self.apply_filter(boolean_array)

            return boolean_array

        else:
            raise ValueError("Unsupported filter. Check docstring")

    def get_sample(self, name, as_PyntCloud=False, **kwargs):
        """Return arbitrary number of points sampled by selected method.

        Parameters
        ----------
        name: str
            One of the available names.
            See below.

        as_PyntCloud: bool, optional
            Default: False
            If True, sampled points will be returned as PyntCloud instance.

        kwargs
            Vary for each name.
            See below.

        Returns
        -------
        sampled_points: (n, 3) ndarray or PyntCloud
            'n' vary for each method. PyntCloud if as_PyntCloud

        Notes
        -----

        Available sampling methods are:

        **REQUIRE MESH**

            mesh_random
                n: int
                    Number of points to be sampled.
                rgb: bool, optional
                    Default: False
                    Indicates if rgb values will be also sampled
                normals: bool, optional
                    Default: False
                    Indicates if normals will be also sampled

        **REQUIRE VOXELGRID**

            ARGS
                voxelgrid: VoxelGrid.id
                    voxelgrid = self.add_structure("voxelgrid", ...)

            voxelgrid_centers

            voxelgrid_centroids

            voxelgrid_nearest
                n: int
                    Number of nearest point per voxel to sample

            voxelgrid_highest


        **USE POINTS**

            points_random
                n: int
                    Number of points to be sampled.
        """
        if name in ALL_SAMPLERS:
            sampler = ALL_SAMPLERS[name](pyntcloud=self, **kwargs)
            sampler.extract_info()
            sample = sampler.compute()

            if as_PyntCloud:
                return PyntCloud(sample)

            return sample

        else:
            raise ValueError("Unsupported sampling method. Check docstring")

    def get_neighbors(self, k=None, r=None, kdtree=None):
        """For each point finds the indices that compose its neighborhood.

        Parameters
        ----------
        k: int, optional
            Default: None
            For "K-nearest neighbor" search.
            Number of nearest neighbors that will be used to build the neighborhood.

        r: float, optional
            Default: None
            For "Fixed-radius neighbors" search.
            Radius of the sphere that will be used to build the neighborhood.

        kdtree: str, optional
            Default: None
            KDTree.id in self.structures.

            - If **kdtree** is None:

            The KDTree will be computed and added to PyntCloud as part of the process.

            - Else:

            The given KDTree will be used for neighbor search.

        Returns
        -------
        neighbors: array-like
            (N, k) ndarray if k is not None.
                Indices of the 'k' nearest neighbors for the 'N' points.
            (N,) ndarray of lists if r is not None.
                Array holding a variable number of indices corresponding
                to the neighbors with distance < r.
        """
        if kdtree is None:
            kdtree_id = self.add_structure("kdtree")
            kdtree = self.structures[kdtree_id]
        else:
            kdtree = self.structures[kdtree]

        if k is not None:
            return k_neighbors(kdtree, k)

        elif r is not None:
            return r_neighbors(kdtree, r)

        else:
            raise ValueError("You must supply 'k' or 'r' values.")

    def get_mesh_vertices(self, rgb=False, normals=False):
        """Decompose triangles of self.mesh from vertices in self.points.

        Returns
        -------
        v1, v2, v3: ndarray
            (N, 3) arrays of vertices so v1[i], v2[i], v3[i] represent the ith triangle
        """
        use_columns = ["x", "y", "z"]
        if rgb:
            use_columns.extend(["red", "green", "blue"])
        if normals:
            use_columns.extend(["nx", "ny", "nz"])

        points = self.points[use_columns].values

        v1 = points[[self.mesh["v1"]]]
        v2 = points[[self.mesh["v2"]]]
        v3 = points[[self.mesh["v3"]]]

        return v1, v2, v3

    def apply_filter(self, boolean_array):
        """Update self.points removing points where filter is False.

        Parameters
        ----------
        boolean_array: ndarray, dtype bool
            len(boolean array) must be equal to len(self.points)
        """
        self.points = self.points.loc[boolean_array].reset_index(drop=True)

    def split_on(self, scalar_field, and_return=False, save_format="ply", save_path=os.getcwd()):
        """Divide the PyntCloud using unique values in given sf.

        This function will generate PyntClouds by grouping points using the unique
        values found in the given scalar field.

        Parameters
        ----------
        scalar_field: str
            Name of the scalar field to be used for splitting.

        and_return: boolean, optional
            Default: False
            If True, return a list with the splits.

        save_format: str, optional
            Default: "ply"
            Extension used to save the generated PyntClouds.
            Must be of one of the formats present in pyntcloud.io.TO

        save_path: str, optional
            Default: "."
            Path where the PyntClouds will be saved.
        """
        scalar_field = self.points[scalar_field]

        splits = {x: PyntCloud(self.points.loc[scalar_field == x]) for x in scalar_field.unique()}

        if not os.path.exists(save_path):
            os.makedirs(save_path)

        for key, val in splits.items():
            val.to_file("{}/{}.{}".format(save_path, key, save_format))

        if and_return:
            return splits

    def _update_points(self, df):
        """Utility function. Implicitly called when self.points is assigned."""
        self.mesh = None
        self.structures = StructuresDict()
        self.__points = df
        self.xyz = self.__points[["x", "y", "z"]].values
        self.centroid = self.xyz.mean(0)

    def plot(self,
             backend="pythreejs",
             width=800,
             height=500,
             background="black",
             mesh=False,
             use_as_color=["red", "green", "blue"],
             initial_point_size=0.0,
             cmap="hsv",
             return_scene=False,
             output_name="pyntcloud_plot",
             polylines={}
             ):
        """Visualize a PyntCloud  using different backends.

        Parameters
        ----------
        backend: {"pythreejs", "threejs"}, optional
            Default: "pythreejs"
            Used to select one of the available libraries for plotting.

        width: int, optional
            Default: 800

        height: int, optional
            Default: 500

        background: str, optional
            Default: "black"
            Used to select the default color of the background.
            In some backends, i.e "pythreejs" the background can be dynamically changed.

        use_as_color: str or ["red", "green", "blue"], optional
            Default: ["red", "green", "blue"]
            Indicates which scalar fields will be used to colorize the rendered
            point cloud.

        initial_point_size: the initial size of each point in the rendered point cloud.
            Can be adjusted after rendering using slider.

        cmap: str, optional
            Default: "hsv"
            Color map that will be used to convert a single scalar field into rgb.
            Check matplotlib cmaps.

        return_scene: bool, optional
            Default: False.
            Used with "pythreejs" backend in order to return the pythreejs.Scene object

        polylines: dict, optional
            Default {}.
            Mapping hexadecimal colors to a list of list(len(3)) representing the points of the polyline.
            Example:
            polylines={
                "0xFFFFFF": [[0, 0, 0], [0, 0, 1]],
                "0xFF00FF": [[1, 0, 0], [1, 0, 1], [1, 1, 1]]
            }

        Returns
        -------
        pythreejs.Scene if return_scene else None
        """
        try:
            colors = self.points[use_as_color].values
        except KeyError:
            colors = None

        if use_as_color != ["red", "green", "blue"] and colors is not None:
            import matplotlib.pyplot as plt
            s_m = plt.cm.ScalarMappable(cmap=cmap)
            colors = s_m.to_rgba(colors)[:, :-1] * 255
        elif colors is None:
            # default color orange
            colors = np.repeat([[255, 125, 0]], self.xyz.shape[0], axis=0)

        colors = colors.astype(np.uint8)

        ptp = self.xyz.ptp()

        if backend == "pythreejs":
            import ipywidgets
            import pythreejs
            from IPython.display import display

            if mesh:
                raise NotImplementedError("Plotting mesh geometry with pythreejs backend is not supported yet.")

            if polylines:
                raise NotImplementedError("Plotting polylines with pythreejs backend is not supported yet.")

            points_geometry = pythreejs.BufferGeometry(
                attributes=dict(
                    position=pythreejs.BufferAttribute(self.xyz, normalized=False),
                    color=pythreejs.BufferAttribute(list(map(tuple, colors)))))

            points_material = pythreejs.PointsMaterial(
                vertexColors='VertexColors')

            points = pythreejs.Points(
                geometry=points_geometry,
                material=points_material,
                position=tuple(self.centroid))

            camera = pythreejs.PerspectiveCamera(
                fov=90,
                aspect=width / height,
                position=tuple(self.centroid + [0, abs(self.xyz.max(0)[1]), abs(self.xyz.max(0)[2]) * 2]),
                up=[0, 0, 1])

            orbit_control = pythreejs.OrbitControls(controlling=camera)
            orbit_control.target = tuple(self.centroid)

            camera.lookAt(tuple(self.centroid))

            scene = pythreejs.Scene(children=[points, camera], background=background)

            renderer = pythreejs.Renderer(
                scene=scene,
                camera=camera,
                controls=[orbit_control],
                width=width,
                height=height)

            display(renderer)

            size = ipywidgets.FloatSlider(value=initial_point_size, min=0.0, max=(ptp / 100), step=(ptp / 1000))
            ipywidgets.jslink((size, 'value'), (points_material, 'size'))

            color = ipywidgets.ColorPicker()
            ipywidgets.jslink((color, 'value'), (scene, 'background'))

            display(ipywidgets.HBox(children=[
                ipywidgets.Label('Background color:'), color, ipywidgets.Label('Point size:'), size]))
            return scene if return_scene else None

        elif backend == "threejs":
            points = pd.DataFrame(self.xyz, columns=["x", "y", "z"])

            for n, i in enumerate(["red", "green", "blue"]):
                points[i] = colors[:, n]

            new_PyntCloud = PyntCloud(points)

            if mesh and self.mesh is not None:
                new_PyntCloud.mesh = self.mesh[["v1", "v2", "v3"]]

            return plot_PyntCloud(
                new_PyntCloud,
                IFrame_shape=(width, height),
                point_size=ptp / 100,
                point_opacity=0.9,
                output_name=output_name,
                polylines=polylines
            )
        else:
            raise NotImplementedError("{} backend is not supported".format(backend))
