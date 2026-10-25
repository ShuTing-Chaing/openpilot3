#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void live_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_9(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_12(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_35(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_32(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_33(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_H(double *in_vec, double *out_7005752570005578961);
void live_err_fun(double *nom_x, double *delta_x, double *out_7589817603843482841);
void live_inv_err_fun(double *nom_x, double *true_x, double *out_4003355797718016078);
void live_H_mod_fun(double *state, double *out_1658232228582318903);
void live_f_fun(double *state, double dt, double *out_8629463197861236502);
void live_F_fun(double *state, double dt, double *out_7158779293866317104);
void live_h_4(double *state, double *unused, double *out_7355301386447911682);
void live_H_4(double *state, double *unused, double *out_6290269275476162458);
void live_h_9(double *state, double *unused, double *out_5571651384589432042);
void live_H_9(double *state, double *unused, double *out_6531458922105753103);
void live_h_10(double *state, double *unused, double *out_8980796449152420986);
void live_H_10(double *state, double *unused, double *out_6948334596317351299);
void live_h_12(double *state, double *unused, double *out_4716386520962411812);
void live_H_12(double *state, double *unused, double *out_7137018390201427363);
void live_h_35(double *state, double *unused, double *out_2680902529338300814);
void live_H_35(double *state, double *unused, double *out_4391455357876413654);
void live_h_32(double *state, double *unused, double *out_3666326907158981297);
void live_H_32(double *state, double *unused, double *out_8012091823137870232);
void live_h_13(double *state, double *unused, double *out_8373431815228625069);
void live_H_13(double *state, double *unused, double *out_1172687039356241799);
void live_h_14(double *state, double *unused, double *out_5571651384589432042);
void live_H_14(double *state, double *unused, double *out_6531458922105753103);
void live_h_33(double *state, double *unused, double *out_3647289326544452457);
void live_H_33(double *state, double *unused, double *out_1240898353237556050);
void live_predict(double *in_x, double *in_P, double *in_Q, double dt);
}