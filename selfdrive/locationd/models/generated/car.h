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
void car_err_fun(double *nom_x, double *delta_x, double *out_2965481454622103238);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_7732790030191075120);
void car_H_mod_fun(double *state, double *out_1644909271350565423);
void car_f_fun(double *state, double dt, double *out_3516311352987958568);
void car_F_fun(double *state, double dt, double *out_8883123696218047910);
void car_h_25(double *state, double *unused, double *out_5647175172865732852);
void car_H_25(double *state, double *unused, double *out_7608646576446748956);
void car_h_24(double *state, double *unused, double *out_527842000710234648);
void car_H_24(double *state, double *unused, double *out_2862137249480239922);
void car_h_30(double *state, double *unused, double *out_5371981110581226963);
void car_H_30(double *state, double *unused, double *out_8319764538755554033);
void car_h_26(double *state, double *unused, double *out_8073089695467479008);
void car_H_26(double *state, double *unused, double *out_3867143257572692732);
void car_h_27(double *state, double *unused, double *out_5796806197050752985);
void car_H_27(double *state, double *unused, double *out_6096170467571610816);
void car_h_29(double *state, double *unused, double *out_4768665225904749446);
void car_H_29(double *state, double *unused, double *out_7809533194441161849);
void car_h_28(double *state, double *unused, double *out_4853296344149090550);
void car_H_28(double *state, double *unused, double *out_5554811862198859193);
void car_h_31(double *state, double *unused, double *out_5489988504514603707);
void car_H_31(double *state, double *unused, double *out_7639292538323709384);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}