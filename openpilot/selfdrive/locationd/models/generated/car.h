#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_err_fun(double *nom_x, double *delta_x, double *out_2314234994522086717);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_8407427781321417370);
void car_H_mod_fun(double *state, double *out_5333563562602869405);
void car_f_fun(double *state, double dt, double *out_1540134498218697658);
void car_F_fun(double *state, double dt, double *out_5336244513521538502);
void car_h_25(double *state, double *unused, double *out_1317641195759651709);
void car_H_25(double *state, double *unused, double *out_8318349668178813102);
void car_h_24(double *state, double *unused, double *out_1577878984148525535);
void car_H_24(double *state, double *unused, double *out_6145700069173313536);
void car_h_30(double *state, double *unused, double *out_132990196869231458);
void car_H_30(double *state, double *unused, double *out_7610061447023489887);
void car_h_26(double *state, double *unused, double *out_7302153237559469355);
void car_H_26(double *state, double *unused, double *out_4576846349304756878);
void car_h_27(double *state, double *unused, double *out_7184605015015087846);
void car_H_27(double *state, double *unused, double *out_8661919314885636818);
void car_h_29(double *state, double *unused, double *out_8265746133860552610);
void car_H_29(double *state, double *unused, double *out_7099830102709097703);
void car_h_28(double *state, double *unused, double *out_2903041173771427338);
void car_H_28(double *state, double *unused, double *out_6264514953930923339);
void car_h_31(double *state, double *unused, double *out_1678751729074259451);
void car_H_31(double *state, double *unused, double *out_3950638247071405402);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}