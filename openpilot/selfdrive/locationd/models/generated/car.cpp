#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_4389956266712543397) {
   out_4389956266712543397[0] = delta_x[0] + nom_x[0];
   out_4389956266712543397[1] = delta_x[1] + nom_x[1];
   out_4389956266712543397[2] = delta_x[2] + nom_x[2];
   out_4389956266712543397[3] = delta_x[3] + nom_x[3];
   out_4389956266712543397[4] = delta_x[4] + nom_x[4];
   out_4389956266712543397[5] = delta_x[5] + nom_x[5];
   out_4389956266712543397[6] = delta_x[6] + nom_x[6];
   out_4389956266712543397[7] = delta_x[7] + nom_x[7];
   out_4389956266712543397[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_3461375902011500942) {
   out_3461375902011500942[0] = -nom_x[0] + true_x[0];
   out_3461375902011500942[1] = -nom_x[1] + true_x[1];
   out_3461375902011500942[2] = -nom_x[2] + true_x[2];
   out_3461375902011500942[3] = -nom_x[3] + true_x[3];
   out_3461375902011500942[4] = -nom_x[4] + true_x[4];
   out_3461375902011500942[5] = -nom_x[5] + true_x[5];
   out_3461375902011500942[6] = -nom_x[6] + true_x[6];
   out_3461375902011500942[7] = -nom_x[7] + true_x[7];
   out_3461375902011500942[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_7556527431228842019) {
   out_7556527431228842019[0] = 1.0;
   out_7556527431228842019[1] = 0.0;
   out_7556527431228842019[2] = 0.0;
   out_7556527431228842019[3] = 0.0;
   out_7556527431228842019[4] = 0.0;
   out_7556527431228842019[5] = 0.0;
   out_7556527431228842019[6] = 0.0;
   out_7556527431228842019[7] = 0.0;
   out_7556527431228842019[8] = 0.0;
   out_7556527431228842019[9] = 0.0;
   out_7556527431228842019[10] = 1.0;
   out_7556527431228842019[11] = 0.0;
   out_7556527431228842019[12] = 0.0;
   out_7556527431228842019[13] = 0.0;
   out_7556527431228842019[14] = 0.0;
   out_7556527431228842019[15] = 0.0;
   out_7556527431228842019[16] = 0.0;
   out_7556527431228842019[17] = 0.0;
   out_7556527431228842019[18] = 0.0;
   out_7556527431228842019[19] = 0.0;
   out_7556527431228842019[20] = 1.0;
   out_7556527431228842019[21] = 0.0;
   out_7556527431228842019[22] = 0.0;
   out_7556527431228842019[23] = 0.0;
   out_7556527431228842019[24] = 0.0;
   out_7556527431228842019[25] = 0.0;
   out_7556527431228842019[26] = 0.0;
   out_7556527431228842019[27] = 0.0;
   out_7556527431228842019[28] = 0.0;
   out_7556527431228842019[29] = 0.0;
   out_7556527431228842019[30] = 1.0;
   out_7556527431228842019[31] = 0.0;
   out_7556527431228842019[32] = 0.0;
   out_7556527431228842019[33] = 0.0;
   out_7556527431228842019[34] = 0.0;
   out_7556527431228842019[35] = 0.0;
   out_7556527431228842019[36] = 0.0;
   out_7556527431228842019[37] = 0.0;
   out_7556527431228842019[38] = 0.0;
   out_7556527431228842019[39] = 0.0;
   out_7556527431228842019[40] = 1.0;
   out_7556527431228842019[41] = 0.0;
   out_7556527431228842019[42] = 0.0;
   out_7556527431228842019[43] = 0.0;
   out_7556527431228842019[44] = 0.0;
   out_7556527431228842019[45] = 0.0;
   out_7556527431228842019[46] = 0.0;
   out_7556527431228842019[47] = 0.0;
   out_7556527431228842019[48] = 0.0;
   out_7556527431228842019[49] = 0.0;
   out_7556527431228842019[50] = 1.0;
   out_7556527431228842019[51] = 0.0;
   out_7556527431228842019[52] = 0.0;
   out_7556527431228842019[53] = 0.0;
   out_7556527431228842019[54] = 0.0;
   out_7556527431228842019[55] = 0.0;
   out_7556527431228842019[56] = 0.0;
   out_7556527431228842019[57] = 0.0;
   out_7556527431228842019[58] = 0.0;
   out_7556527431228842019[59] = 0.0;
   out_7556527431228842019[60] = 1.0;
   out_7556527431228842019[61] = 0.0;
   out_7556527431228842019[62] = 0.0;
   out_7556527431228842019[63] = 0.0;
   out_7556527431228842019[64] = 0.0;
   out_7556527431228842019[65] = 0.0;
   out_7556527431228842019[66] = 0.0;
   out_7556527431228842019[67] = 0.0;
   out_7556527431228842019[68] = 0.0;
   out_7556527431228842019[69] = 0.0;
   out_7556527431228842019[70] = 1.0;
   out_7556527431228842019[71] = 0.0;
   out_7556527431228842019[72] = 0.0;
   out_7556527431228842019[73] = 0.0;
   out_7556527431228842019[74] = 0.0;
   out_7556527431228842019[75] = 0.0;
   out_7556527431228842019[76] = 0.0;
   out_7556527431228842019[77] = 0.0;
   out_7556527431228842019[78] = 0.0;
   out_7556527431228842019[79] = 0.0;
   out_7556527431228842019[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_4680561550399641935) {
   out_4680561550399641935[0] = state[0];
   out_4680561550399641935[1] = state[1];
   out_4680561550399641935[2] = state[2];
   out_4680561550399641935[3] = state[3];
   out_4680561550399641935[4] = state[4];
   out_4680561550399641935[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_4680561550399641935[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_4680561550399641935[7] = state[7];
   out_4680561550399641935[8] = state[8];
}
void F_fun(double *state, double dt, double *out_3969396675874881206) {
   out_3969396675874881206[0] = 1;
   out_3969396675874881206[1] = 0;
   out_3969396675874881206[2] = 0;
   out_3969396675874881206[3] = 0;
   out_3969396675874881206[4] = 0;
   out_3969396675874881206[5] = 0;
   out_3969396675874881206[6] = 0;
   out_3969396675874881206[7] = 0;
   out_3969396675874881206[8] = 0;
   out_3969396675874881206[9] = 0;
   out_3969396675874881206[10] = 1;
   out_3969396675874881206[11] = 0;
   out_3969396675874881206[12] = 0;
   out_3969396675874881206[13] = 0;
   out_3969396675874881206[14] = 0;
   out_3969396675874881206[15] = 0;
   out_3969396675874881206[16] = 0;
   out_3969396675874881206[17] = 0;
   out_3969396675874881206[18] = 0;
   out_3969396675874881206[19] = 0;
   out_3969396675874881206[20] = 1;
   out_3969396675874881206[21] = 0;
   out_3969396675874881206[22] = 0;
   out_3969396675874881206[23] = 0;
   out_3969396675874881206[24] = 0;
   out_3969396675874881206[25] = 0;
   out_3969396675874881206[26] = 0;
   out_3969396675874881206[27] = 0;
   out_3969396675874881206[28] = 0;
   out_3969396675874881206[29] = 0;
   out_3969396675874881206[30] = 1;
   out_3969396675874881206[31] = 0;
   out_3969396675874881206[32] = 0;
   out_3969396675874881206[33] = 0;
   out_3969396675874881206[34] = 0;
   out_3969396675874881206[35] = 0;
   out_3969396675874881206[36] = 0;
   out_3969396675874881206[37] = 0;
   out_3969396675874881206[38] = 0;
   out_3969396675874881206[39] = 0;
   out_3969396675874881206[40] = 1;
   out_3969396675874881206[41] = 0;
   out_3969396675874881206[42] = 0;
   out_3969396675874881206[43] = 0;
   out_3969396675874881206[44] = 0;
   out_3969396675874881206[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_3969396675874881206[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_3969396675874881206[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_3969396675874881206[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_3969396675874881206[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_3969396675874881206[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_3969396675874881206[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_3969396675874881206[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_3969396675874881206[53] = -9.8100000000000005*dt;
   out_3969396675874881206[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_3969396675874881206[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_3969396675874881206[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3969396675874881206[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3969396675874881206[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_3969396675874881206[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_3969396675874881206[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_3969396675874881206[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3969396675874881206[62] = 0;
   out_3969396675874881206[63] = 0;
   out_3969396675874881206[64] = 0;
   out_3969396675874881206[65] = 0;
   out_3969396675874881206[66] = 0;
   out_3969396675874881206[67] = 0;
   out_3969396675874881206[68] = 0;
   out_3969396675874881206[69] = 0;
   out_3969396675874881206[70] = 1;
   out_3969396675874881206[71] = 0;
   out_3969396675874881206[72] = 0;
   out_3969396675874881206[73] = 0;
   out_3969396675874881206[74] = 0;
   out_3969396675874881206[75] = 0;
   out_3969396675874881206[76] = 0;
   out_3969396675874881206[77] = 0;
   out_3969396675874881206[78] = 0;
   out_3969396675874881206[79] = 0;
   out_3969396675874881206[80] = 1;
}
void h_25(double *state, double *unused, double *out_22325292270229792) {
   out_22325292270229792[0] = state[6];
}
void H_25(double *state, double *unused, double *out_364810601745017786) {
   out_364810601745017786[0] = 0;
   out_364810601745017786[1] = 0;
   out_364810601745017786[2] = 0;
   out_364810601745017786[3] = 0;
   out_364810601745017786[4] = 0;
   out_364810601745017786[5] = 0;
   out_364810601745017786[6] = 1;
   out_364810601745017786[7] = 0;
   out_364810601745017786[8] = 0;
}
void h_24(double *state, double *unused, double *out_4541032309889520162) {
   out_4541032309889520162[0] = state[4];
   out_4541032309889520162[1] = state[5];
}
void H_24(double *state, double *unused, double *out_4381698725221491248) {
   out_4381698725221491248[0] = 0;
   out_4381698725221491248[1] = 0;
   out_4381698725221491248[2] = 0;
   out_4381698725221491248[3] = 0;
   out_4381698725221491248[4] = 1;
   out_4381698725221491248[5] = 0;
   out_4381698725221491248[6] = 0;
   out_4381698725221491248[7] = 0;
   out_4381698725221491248[8] = 0;
   out_4381698725221491248[9] = 0;
   out_4381698725221491248[10] = 0;
   out_4381698725221491248[11] = 0;
   out_4381698725221491248[12] = 0;
   out_4381698725221491248[13] = 0;
   out_4381698725221491248[14] = 1;
   out_4381698725221491248[15] = 0;
   out_4381698725221491248[16] = 0;
   out_4381698725221491248[17] = 0;
}
void h_30(double *state, double *unused, double *out_179511960621358937) {
   out_179511960621358937[0] = state[4];
}
void H_30(double *state, double *unused, double *out_2883143560252266413) {
   out_2883143560252266413[0] = 0;
   out_2883143560252266413[1] = 0;
   out_2883143560252266413[2] = 0;
   out_2883143560252266413[3] = 0;
   out_2883143560252266413[4] = 1;
   out_2883143560252266413[5] = 0;
   out_2883143560252266413[6] = 0;
   out_2883143560252266413[7] = 0;
   out_2883143560252266413[8] = 0;
}
void h_26(double *state, double *unused, double *out_2441156412715266355) {
   out_2441156412715266355[0] = state[7];
}
void H_26(double *state, double *unused, double *out_3376692717129038438) {
   out_3376692717129038438[0] = 0;
   out_3376692717129038438[1] = 0;
   out_3376692717129038438[2] = 0;
   out_3376692717129038438[3] = 0;
   out_3376692717129038438[4] = 0;
   out_3376692717129038438[5] = 0;
   out_3376692717129038438[6] = 0;
   out_3376692717129038438[7] = 1;
   out_3376692717129038438[8] = 0;
}
void h_27(double *state, double *unused, double *out_1825768382205575548) {
   out_1825768382205575548[0] = state[3];
}
void H_27(double *state, double *unused, double *out_5106737631436209630) {
   out_5106737631436209630[0] = 0;
   out_5106737631436209630[1] = 0;
   out_5106737631436209630[2] = 0;
   out_5106737631436209630[3] = 1;
   out_5106737631436209630[4] = 0;
   out_5106737631436209630[5] = 0;
   out_5106737631436209630[6] = 0;
   out_5106737631436209630[7] = 0;
   out_5106737631436209630[8] = 0;
}
void h_29(double *state, double *unused, double *out_7182274664414424716) {
   out_7182274664414424716[0] = state[1];
}
void H_29(double *state, double *unused, double *out_3393374904566658597) {
   out_3393374904566658597[0] = 0;
   out_3393374904566658597[1] = 1;
   out_3393374904566658597[2] = 0;
   out_3393374904566658597[3] = 0;
   out_3393374904566658597[4] = 0;
   out_3393374904566658597[5] = 0;
   out_3393374904566658597[6] = 0;
   out_3393374904566658597[7] = 0;
   out_3393374904566658597[8] = 0;
}
void h_28(double *state, double *unused, double *out_8544195375055394932) {
   out_8544195375055394932[0] = state[0];
}
void H_28(double *state, double *unused, double *out_1689024112502871977) {
   out_1689024112502871977[0] = 1;
   out_1689024112502871977[1] = 0;
   out_1689024112502871977[2] = 0;
   out_1689024112502871977[3] = 0;
   out_1689024112502871977[4] = 0;
   out_1689024112502871977[5] = 0;
   out_1689024112502871977[6] = 0;
   out_1689024112502871977[7] = 0;
   out_1689024112502871977[8] = 0;
}
void h_31(double *state, double *unused, double *out_3962481313096036258) {
   out_3962481313096036258[0] = state[8];
}
void H_31(double *state, double *unused, double *out_4002900819362389914) {
   out_4002900819362389914[0] = 0;
   out_4002900819362389914[1] = 0;
   out_4002900819362389914[2] = 0;
   out_4002900819362389914[3] = 0;
   out_4002900819362389914[4] = 0;
   out_4002900819362389914[5] = 0;
   out_4002900819362389914[6] = 0;
   out_4002900819362389914[7] = 0;
   out_4002900819362389914[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_4389956266712543397) {
  err_fun(nom_x, delta_x, out_4389956266712543397);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_3461375902011500942) {
  inv_err_fun(nom_x, true_x, out_3461375902011500942);
}
void car_H_mod_fun(double *state, double *out_7556527431228842019) {
  H_mod_fun(state, out_7556527431228842019);
}
void car_f_fun(double *state, double dt, double *out_4680561550399641935) {
  f_fun(state,  dt, out_4680561550399641935);
}
void car_F_fun(double *state, double dt, double *out_3969396675874881206) {
  F_fun(state,  dt, out_3969396675874881206);
}
void car_h_25(double *state, double *unused, double *out_22325292270229792) {
  h_25(state, unused, out_22325292270229792);
}
void car_H_25(double *state, double *unused, double *out_364810601745017786) {
  H_25(state, unused, out_364810601745017786);
}
void car_h_24(double *state, double *unused, double *out_4541032309889520162) {
  h_24(state, unused, out_4541032309889520162);
}
void car_H_24(double *state, double *unused, double *out_4381698725221491248) {
  H_24(state, unused, out_4381698725221491248);
}
void car_h_30(double *state, double *unused, double *out_179511960621358937) {
  h_30(state, unused, out_179511960621358937);
}
void car_H_30(double *state, double *unused, double *out_2883143560252266413) {
  H_30(state, unused, out_2883143560252266413);
}
void car_h_26(double *state, double *unused, double *out_2441156412715266355) {
  h_26(state, unused, out_2441156412715266355);
}
void car_H_26(double *state, double *unused, double *out_3376692717129038438) {
  H_26(state, unused, out_3376692717129038438);
}
void car_h_27(double *state, double *unused, double *out_1825768382205575548) {
  h_27(state, unused, out_1825768382205575548);
}
void car_H_27(double *state, double *unused, double *out_5106737631436209630) {
  H_27(state, unused, out_5106737631436209630);
}
void car_h_29(double *state, double *unused, double *out_7182274664414424716) {
  h_29(state, unused, out_7182274664414424716);
}
void car_H_29(double *state, double *unused, double *out_3393374904566658597) {
  H_29(state, unused, out_3393374904566658597);
}
void car_h_28(double *state, double *unused, double *out_8544195375055394932) {
  h_28(state, unused, out_8544195375055394932);
}
void car_H_28(double *state, double *unused, double *out_1689024112502871977) {
  H_28(state, unused, out_1689024112502871977);
}
void car_h_31(double *state, double *unused, double *out_3962481313096036258) {
  h_31(state, unused, out_3962481313096036258);
}
void car_H_31(double *state, double *unused, double *out_4002900819362389914) {
  H_31(state, unused, out_4002900819362389914);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
