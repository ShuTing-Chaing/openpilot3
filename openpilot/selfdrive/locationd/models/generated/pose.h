#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_707370688016723266);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_6651301100166098558);
void pose_H_mod_fun(double *state, double *out_95794323830548291);
void pose_f_fun(double *state, double dt, double *out_5629211650094912184);
void pose_F_fun(double *state, double dt, double *out_5949544175274232713);
void pose_h_4(double *state, double *unused, double *out_4850019821057066741);
void pose_H_4(double *state, double *unused, double *out_9040155989888369633);
void pose_h_10(double *state, double *unused, double *out_9215908307232531236);
void pose_H_10(double *state, double *unused, double *out_1931647352710355575);
void pose_h_13(double *state, double *unused, double *out_246971447327183336);
void pose_H_13(double *state, double *unused, double *out_5827882164556036832);
void pose_h_14(double *state, double *unused, double *out_3722913904389418623);
void pose_H_14(double *state, double *unused, double *out_5076915133548885104);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}