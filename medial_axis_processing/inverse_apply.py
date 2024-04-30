import numpy as np
from pygel3d import hmesh
from commons.medial_axis import MedialAxis
from scipy.spatial.transform import Rotation as R


def __get_local_basis(v0, v1, n, inverse_normal=False):
    if inverse_normal:
        n = -n

    b0 = v1 - v0
    b0 /= np.linalg.norm(b0)
    b1 = np.cross(n, b0)
    return b0, b1, n


def __project_point_to_basis(point, vertex, basis):
    # get point coordinates in local basis
    v_p = point - vertex
    return np.dot(v_p, basis[0]), np.dot(v_p, basis[1]), np.dot(v_p, basis[2])


def __update_point(vertex_new, local_coords, new_basis):
    # retrieve global coordinates from local basis coordinates
    return vertex_new + local_coords[0] * new_basis[0] + local_coords[1] * new_basis[1] + local_coords[2] * new_basis[2]


def __compute_tangents(curve):
    # Approximate tangent vectors by finite differences
    tangents = np.gradient(curve, axis=0)
    # Normalize tangent vectors
    tangents /= np.linalg.norm(tangents, axis=1)[:, np.newaxis]
    return tangents


def __inverse_apply_sheet(ma: MedialAxis, updated_sheet_positions: np.ndarray):
    """Applies the transformation of the medial sheet onto corresponding inner and outer points.
       Does this by projecting the points to the local basis of the medial sheet vertex, and then updating the point"""
    positions = ma.sheet.positions()

    updated_sheet = hmesh.Manifold(ma.sheet)
    updated_sheet.positions()[:] = updated_sheet_positions

    new_outer_pos = np.copy(ma.outer_points)

    for vid in ma.sheet.vertices():
        neighbor = ma.sheet.circulate_vertex(vid)[0]

        for outer_idx in ma.sheet_correspondences[vid]:
            outer_point = ma.outer_points[outer_idx]

            n_old = ma.sheet.vertex_normal(vid)
            # diff = outer_point - positions[vid]
            # angle = np.arccos(np.dot(diff, n_old) / np.linalg.norm(diff))
            basis_old = __get_local_basis(positions[vid], positions[neighbor], n_old)

            n_new = updated_sheet.vertex_normal(vid)
            basis_new = __get_local_basis(updated_sheet_positions[vid], updated_sheet_positions[neighbor], n_new)

            local_coords = __project_point_to_basis(outer_point, positions[vid], basis_old)
            new_pos = __update_point(updated_sheet_positions[vid], local_coords, basis_new)
            new_outer_pos[outer_idx] = new_pos

    ma.sheet.positions()[:] = updated_sheet_positions
    ma.inner_points[~ma.curve_indices] = updated_sheet_positions[ma.inner_indices[~ma.curve_indices]]
    ma.graph.positions()[~ma.curve_indices] = updated_sheet_positions[ma.inner_indices[~ma.curve_indices]]
    ma.outer_points = new_outer_pos


def parallel_transport(old_curve_pos: np.ndarray, new_curve_pos: np.ndarray, outer_points: list[np.ndarray]):
    """Given the original curve point positions, their updated positions, and a list of corresponding outer points for
       each curve point, returns the parallel transport of the outer points along the curve to the updated positions."""
    orig_tangents = __compute_tangents(old_curve_pos)
    new_tangents = __compute_tangents(new_curve_pos)
    new_outer_points_list = []

    for i in range(len(old_curve_pos)):
        axis = np.cross(orig_tangents[i], new_tangents[i])
        axis_length = np.linalg.norm(axis)
        axis /= axis_length
        angle = np.arccos(np.clip(np.dot(orig_tangents[i], new_tangents[i]), -1.0, 1.0))
        rotation = R.from_rotvec(axis * angle)
        new_outer_points = [
            rotation.apply(point - old_curve_pos[i]) + new_curve_pos[i]
            for point in outer_points[i]
        ]
        new_outer_points_list.append(new_outer_points)

    return new_outer_points_list


def apply_inverse_medial_axis_transform(
        medial_axis: MedialAxis,
        updated_sheet_positions: np.ndarray,
        updated_curve_positions: list[np.ndarray]
):
    __inverse_apply_sheet(medial_axis, updated_sheet_positions)
    medial_axis.surface.positions()[:] = medial_axis.outer_points

    for i, curve in enumerate(medial_axis.curves):
        inner_points = medial_axis.inner_points[curve]
        outer_points_indices = medial_axis.correspondences[curve]

        outer_points = []
        for indices in outer_points_indices:
            outer_points.append(medial_axis.outer_points[indices])

        new_outer_points = parallel_transport(
            inner_points,
            updated_curve_positions[i],
            outer_points
        )
        medial_axis.inner_points[curve] = updated_curve_positions[i]
        medial_axis.graph.positions()[curve] = updated_curve_positions[i]
        for j, indices in enumerate(outer_points_indices):
            if len(indices) == 0:
                continue
            medial_axis.outer_points[indices] = new_outer_points[j]
            medial_axis.surface.positions()[indices] = new_outer_points[j]
