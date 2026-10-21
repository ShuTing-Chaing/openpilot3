#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_2178224858840209361);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_4618004895414237312);
void pose_H_mod_fun(double *state, double *out_6893734767702127169);
void pose_f_fun(double *state, double dt, double *out_6153064126878909392);
void pose_F_fun(double *state, double dt, double *out_3286506466705227237);
void pose_h_4(double *state, double *unused, double *out_3648588459832896841);
void pose_H_4(double *state, double *unused, double *out_5695787285819229065);
void pose_h_10(double *state, double *unused, double *out_7983794647515202819);
void pose_H_10(double *state, double *unused, double *out_3032931921094903591);
void pose_h_13(double *state, double *unused, double *out_1190906095138799015);
void pose_H_13(double *state, double *unused, double *out_2483513460486896264);
void pose_h_14(double *state, double *unused, double *out_4979926043979174598);
void pose_H_14(double *state, double *unused, double *out_8778575718114601361);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}