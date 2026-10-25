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
void car_err_fun(double *nom_x, double *delta_x, double *out_4389956266712543397);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_3461375902011500942);
void car_H_mod_fun(double *state, double *out_7556527431228842019);
void car_f_fun(double *state, double dt, double *out_4680561550399641935);
void car_F_fun(double *state, double dt, double *out_3969396675874881206);
void car_h_25(double *state, double *unused, double *out_22325292270229792);
void car_H_25(double *state, double *unused, double *out_364810601745017786);
void car_h_24(double *state, double *unused, double *out_4541032309889520162);
void car_H_24(double *state, double *unused, double *out_4381698725221491248);
void car_h_30(double *state, double *unused, double *out_179511960621358937);
void car_H_30(double *state, double *unused, double *out_2883143560252266413);
void car_h_26(double *state, double *unused, double *out_2441156412715266355);
void car_H_26(double *state, double *unused, double *out_3376692717129038438);
void car_h_27(double *state, double *unused, double *out_1825768382205575548);
void car_H_27(double *state, double *unused, double *out_5106737631436209630);
void car_h_29(double *state, double *unused, double *out_7182274664414424716);
void car_H_29(double *state, double *unused, double *out_3393374904566658597);
void car_h_28(double *state, double *unused, double *out_8544195375055394932);
void car_H_28(double *state, double *unused, double *out_1689024112502871977);
void car_h_31(double *state, double *unused, double *out_3962481313096036258);
void car_H_31(double *state, double *unused, double *out_4002900819362389914);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}